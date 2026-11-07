"""Taskbar notification-area icon, owned by a dedicated message-pump thread.

Left click (or keyboard select) raises the main window; right click reports
the cursor position so the shell can pop the styled menu above the icon.
The icon re-registers itself after Explorer restarts via TaskbarCreated.
"""
import ctypes
import threading
from ctypes import wintypes

import win32api
import win32con
import win32gui

from core.config import APP_NAME, BASE_DIR, RESOURCE_DIR
from core.logger import error, info

NIM_ADD, NIM_SETVERSION, NIM_DELETE = 0, 4, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
NIN_SELECT, NIN_KEYSELECT = 0x402, 0x403
WM_CONTEXTMENU = 0x007B
IMAGE_ICON = 1
LR_DEFAULTSIZE, LR_LOADFROMFILE = 0x40, 0x10
ICON_PATHS = (RESOURCE_DIR / "ui" / "web" / f"{APP_NAME}.ico", BASE_DIR / "build" / f"{APP_NAME}.ico")


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cb_size", wintypes.DWORD), ("h_wnd", wintypes.HWND), ("u_id", wintypes.UINT),
        ("u_flags", wintypes.UINT), ("u_callback_message", wintypes.UINT),
        ("h_icon", wintypes.HICON), ("sz_tip", wintypes.WCHAR * 128),
        ("dw_state", wintypes.DWORD), ("dw_state_mask", wintypes.DWORD),
        ("sz_info", wintypes.WCHAR * 256), ("u_version", wintypes.UINT),
        ("sz_info_title", wintypes.WCHAR * 64), ("dw_info_flags", wintypes.DWORD),
    ]


def _xy(lparam: int) -> tuple[int, int]:
    return ctypes.c_short(lparam & 0xFFFF).value, ctypes.c_short((lparam >> 16) & 0xFFFF).value


class TrayIcon:
    def __init__(self, on_select, on_menu):
        self._on_select = on_select
        self._on_menu = on_menu
        self._hwnd = None
        self._callback = win32con.WM_APP + 1
        self._taskbar_created = None
        self._ready = threading.Event()

    def start(self):
        threading.Thread(target=self._pump, daemon=True).start()
        if not self._ready.wait(timeout=5):
            error("tray icon did not start")

    def destroy(self):
        hwnd, self._hwnd = self._hwnd, None
        if hwnd is not None:
            win32api.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

    def _pump(self):
        try:
            window_class = win32gui.WNDCLASS()
            window_class.hInstance = win32api.GetModuleHandle(None)
            window_class.lpszClassName = f"{APP_NAME}Tray"
            window_class.lpfnWndProc = self._wndproc
            win32gui.RegisterClass(window_class)
            self._taskbar_created = win32gui.RegisterWindowMessage("TaskbarCreated")
            self._hwnd = win32gui.CreateWindow(
                window_class.lpszClassName, f"{APP_NAME} Tray", 0, 0, 0, 0, 0,
                None, None, window_class.hInstance, None)
            self._add()
            self._ready.set()
            info("tray icon active")
            win32gui.PumpMessages()
        except Exception as exc:
            error(f"tray pump failed: {type(exc).__name__}: {exc}")
            self._ready.set()

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == self._taskbar_created:
            self._add()
        elif msg == self._callback:
            # NOTIFYICON_VERSION_4 layout: LOWORD(lparam) = event, wparam = cursor point.
            event = lparam & 0xFFFF
            if event in (NIN_SELECT, NIN_KEYSELECT):
                self._on_select()
            elif event == WM_CONTEXTMENU:
                self._on_menu(*_xy(wparam))
        elif msg == win32con.WM_DESTROY:
            self._delete()
            win32gui.PostQuitMessage(0)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _add(self):
        if self._hwnd is None:
            return
        data = NOTIFYICONDATAW()
        data.cb_size = ctypes.sizeof(data)
        data.h_wnd = self._hwnd
        data.u_id = 1
        data.u_flags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.u_callback_message = self._callback
        data.h_icon = self._load_icon()
        data.sz_tip = APP_NAME
        shell32 = ctypes.windll.shell32
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data))
        data.u_version = 4
        shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(data))

    def _delete(self):
        data = NOTIFYICONDATAW()
        data.cb_size = ctypes.sizeof(data)
        data.h_wnd = self._hwnd
        data.u_id = 1
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))

    @staticmethod
    def _load_icon():
        for path in ICON_PATHS:
            if path.exists():
                hicon = ctypes.windll.user32.LoadImageW(
                    None, str(path), IMAGE_ICON, 0, 0, LR_DEFAULTSIZE | LR_LOADFROMFILE)
                if hicon:
                    return hicon
        return win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
