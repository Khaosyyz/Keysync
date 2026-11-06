"""Desktop shell: main window + recording overlay, both rendered by WebView2.

Python -> JS: events are queued and pushed by one dispatcher thread, so session
threads never block on the UI thread. JS -> Python: the Api classes below.
The overlay never takes focus (WS_EX_NOACTIVATE) so injection still lands in
the window the user was typing in. The window is transparent only while its
own surface stays untouched beneath the WebView2 layer: its WinForms layers
never paint a background, and every resize discards the old client pixels
(SWP_NOCOPYBITS) instead of copying them, because the copy loses transparency.
"""
import ctypes
import json
import queue
import threading

import sounddevice as sd
import soundfile as sf
import webview
import win32api
import win32con
import win32gui

from core.config import HOTKEY_VK, RESOURCE_DIR, settings
from core.engine import transcribe_file
from core.history_store import audio_path, delete_record, load_history, update_text
from core.hotwords import add_hotword, load_hotwords, remove_hotword, update_hotword
from core.logger import error, info
from core.meter import Meter
from core.microphone import default_input_name, list_input_names
from core.models import ModelDownload
from core.output_sink import copy_text
from ui.chrome import hide_caption, hwnd_of, paint_caption

WEB_DIR = RESOURCE_DIR / "ui" / "web"

PREFS = {
    "theme": ("ui.theme", ("system", "light", "dark")),
    "language": ("ui.language", ("en", "zh")),
    "hotkey": ("hotkey.vk", tuple(HOTKEY_VK)),
    "polish_enabled": ("polish.enabled", (True, False)),
    "polish_format": ("polish.format", ("openai", "gemini", "anthropic")),
    "polish_baseurl": ("polish.baseurl", None),
    "polish_apikey": ("polish.apikey", None),
    "polish_models": ("polish.models", None),
    "polish_model": ("polish.model", None),
    "polish_prompt": ("polish.prompt", None),
}

_user32 = ctypes.WinDLL("user32")
_user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
_user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + [ctypes.c_int] * 4 + [ctypes.c_uint]
_user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
HWND_TOPMOST = ctypes.c_void_p(-1)

METER_EVENTS = {"level", "meter_error"}
MAIN_EVENTS = {"result", "model"}
OVERLAY_EVENTS = {"recording", "level", "transcribing", "polishing", "result", "error", "model_missing", "config"}


def _work_area() -> tuple[int, int, int, int]:
    monitor = win32api.MonitorFromWindow(win32gui.GetForegroundWindow(), win32con.MONITOR_DEFAULTTONEAREST)
    return win32api.GetMonitorInfo(monitor)["Work"]


def _suppress_background(control):
    """Stops a WinForms control and its children from ever painting a background.

    The overlay's transparency comes from the WebView2 layer alone; any colour
    painted beneath it (WinForms fills newly exposed area when the window
    grows) shows through the rounded corners. UserPaint + AllPaintingInWmPaint
    keep WM_ERASEBKGND from erasing, Opaque skips the background pass of
    WM_PAINT. SetStyle is protected, hence reflection."""
    import clr
    from System import Array, Object
    from System.Reflection import BindingFlags
    from System.Windows.Forms import Control, ControlStyles

    set_style = clr.GetClrType(Control).GetMethod("SetStyle", BindingFlags.Instance | BindingFlags.NonPublic)
    pending = [control]
    while pending:
        current = pending.pop()
        for style in (ControlStyles.UserPaint, ControlStyles.AllPaintingInWmPaint, ControlStyles.Opaque):
            set_style.Invoke(current, Array[Object]([style, True]))
        pending.extend(current.Controls)


def _ui_config() -> dict:
    return {key: settings.get(path) for key, (path, _) in PREFS.items()}


def _polish_config() -> dict:
    return {key: settings.get(f"polish.{key}")
            for key in ("enabled", "format", "baseurl", "apikey", "models", "model", "prompt")}


class _Dispatcher:
    """Serialises Python -> JS events; a backlog of meter updates is collapsed."""

    def __init__(self, window):
        self._window = window
        self._q = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def push(self, event: str, payload: dict):
        self._q.put((event, payload))

    def _run(self):
        while True:
            event, payload = self._q.get()
            if event == "level" and not self._q.empty():
                continue
            detail = json.dumps(payload, ensure_ascii=False)
            try:
                self._window.run_js(
                    f"window.dispatchEvent(new CustomEvent('ks:{event}', {{detail: {detail}}}))")
            except Exception as exc:
                error(f"ui dispatch {event} failed: {type(exc).__name__}: {exc}")


class MainApi:
    def __init__(self, shell):
        self._shell = shell

    def bootstrap(self):
        return {
            **_ui_config(),
            "hotkeys": list(HOTKEY_VK),
            "onboarded": bool(settings.get("onboarding.completed")),
            "mic": settings.get("audio.device_name") or default_input_name(),
            "retention_days": settings.get("history.retention_days"),
            "hotword_max_count": settings.get("engine.hotword_max_count"),
            "hotword_max_length": settings.get("engine.hotword_max_length"),
            "history": load_history(),
            "hotwords": load_hotwords(),
            "model": self._shell.models.snapshot(),
            "polish": _polish_config(),
        }

    def log_error(self, message: str):
        error(f"main window script: {message}")

    def ready(self):
        self._shell.mount_overlay()
        hide_caption(hwnd_of(self._shell.main))
        self._shell.main.show()

    def set_chrome(self, caption: list[int], dark: bool):
        paint_caption(hwnd_of(self._shell.main), caption, dark)

    def update_setting(self, key: str, value):
        path, allowed = PREFS[key]
        if allowed is not None and value not in allowed:
            raise ValueError(f"invalid {key}: {value!r}")
        settings.set(path, value)
        info(f"setting {path} = {value}")
        config = {**_ui_config(), "polish": _polish_config()}
        self._shell.emit("config", config)
        return config

    def suspend_hotkey(self, suspended: bool):
        self._shell.watcher.suspended = suspended

    def list_mics(self):
        return list_input_names()

    def set_mic(self, name: str):
        settings.set("audio.device_name", "" if name == default_input_name() else name)
        info(f"audio.device_name = {name!r}")
        return {"mic": settings.get("audio.device_name") or default_input_name()}

    def complete_onboarding(self):
        settings.set("onboarding.completed", True)
        info("onboarding completed")
        return {"onboarded": True}

    def download_models(self):
        return self._shell.models.start()

    def meter_start(self):
        self._shell._metering = True
        self._shell.meter.start()

    def meter_stop(self):
        self._shell._metering = False
        self._shell.meter.stop()

    def copy(self, text: str):
        copy_text(text)

    def play(self, entry_id: str):
        data, rate = sf.read(str(audio_path(entry_id)), dtype="float32")
        sd.play(data, rate)

    def stop(self):
        sd.stop()

    def retranscribe(self, entry_id: str):
        record = update_text(entry_id, transcribe_file(audio_path(entry_id)))
        info(f"retranscribed {entry_id}: {record['text'][:40]}")
        return record

    def delete(self, entry_id: str):
        delete_record(entry_id)
        info(f"history deleted: {entry_id}")

    def add_word(self, word: str):
        return add_hotword(word)

    def update_word(self, old: str, new: str):
        return update_hotword(old, new)

    def remove_word(self, word: str):
        return remove_hotword(word)


class OverlayApi:
    def __init__(self, shell):
        self._shell = shell

    def bootstrap(self):
        return {
            **_ui_config(),
            "result_ms": float(settings.get("ui.overlay_result_duration_s")) * 1000,
            "notice_ms": float(settings.get("ui.overlay_notice_duration_s")) * 1000,
            "delivered_ms": float(settings.get("ui.overlay_delivered_duration_s")) * 1000,
            "load_ms": float(settings.get("ui.overlay_load_s")) * 1000,
            "polish_ms": float(settings.get("polish.simulate_delay_s")) * 1000,
        }

    def fit(self, width: float, height: float, scale: float):
        w, h = round(width * scale), round(height * scale)
        left, _, right, bottom = _work_area()
        x = left + (right - left - w) // 2
        y = bottom - h - round(float(settings.get("ui.overlay_bottom_margin_px")) * scale)
        _user32.SetWindowPos(self._shell.overlay_hwnd, HWND_TOPMOST, x, y, w, h,
                             win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW | win32con.SWP_NOCOPYBITS)

    def hide(self):
        _user32.ShowWindow(self._shell.overlay_hwnd, win32con.SW_HIDE)

    def download_models(self):
        self._shell.models.start()

    def copy(self, text: str):
        copy_text(text)

    def log_error(self, message: str):
        error(f"overlay script: {message}")


class Shell:
    def __init__(self, watcher):
        self.watcher = watcher
        self.main = webview.create_window(
            "KeySync", str(WEB_DIR / "index.html"), js_api=MainApi(self),
            width=int(settings.get("ui.window_width")),
            height=int(settings.get("ui.window_height")),
            min_size=(int(settings.get("ui.window_min_width")),
                      int(settings.get("ui.window_min_height"))),
            hidden=True, text_select=True)
        self.overlay = webview.create_window(
            "KeySync Overlay", str(WEB_DIR / "overlay.html"), js_api=OverlayApi(self),
            frameless=True, easy_drag=False, resizable=False, hidden=True, shadow=False,
            on_top=True, text_select=True, min_size=(0, 0), transparent=True)
        self.overlay_hwnd = 0
        self.meter = Meter(self.emit)
        self.models = ModelDownload(self.emit)
        self._metering = False
        self._main_events = _Dispatcher(self.main)
        self._overlay_events = _Dispatcher(self.overlay)
        self.main.events.closed += self.overlay.destroy

    def mount_overlay(self):
        _suppress_background(self.overlay.native)
        hwnd = hwnd_of(self.overlay)
        style = _user32.GetWindowLongPtrW(hwnd, win32con.GWL_EXSTYLE)
        _user32.SetWindowLongPtrW(hwnd, win32con.GWL_EXSTYLE,
                                  (style | win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_NOACTIVATE)
                                  & ~win32con.WS_EX_APPWINDOW)
        _user32.ShowWindow(hwnd, win32con.SW_HIDE)
        self.overlay_hwnd = hwnd

    def emit(self, event: str, payload: dict):
        metered = self._metering and event in METER_EVENTS
        if metered or event in MAIN_EVENTS:
            self._main_events.push(event, payload)
        if not metered and event in OVERLAY_EVENTS:
            self._overlay_events.push(event, payload)

    def run(self):
        webview.start(gui="edgechromium")
