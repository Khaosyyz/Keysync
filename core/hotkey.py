"""Hotkey polling loop (GetAsyncKeyState, no LL hook).

The configured key is re-read every poll, so a change in settings applies at
once; `suspended` mutes the watcher while the settings page captures a key.

A lone Alt press-and-release makes the focused window enter menu mode (its UI
thread sits in a modal menu loop until the next key). An unassigned key tapped
while Alt is still down cancels that, the same mask AutoHotkey uses.
"""
import time

import win32api
import win32con

from core.config import MENU_KEYS, settings
from core.logger import info


class HotkeyWatcher:
    def __init__(self, on_press):
        self._on_press = on_press
        self._interval = float(settings.get("hotkey.poll_interval_ms")) / 1000.0
        self._release_timeout = float(settings.get("hotkey.release_timeout_ms")) / 1000.0
        self._running = False
        self.suspended = False

    def stop(self):
        self._running = False

    @staticmethod
    def _mask_menu():
        mask = int(settings.get("hotkey.menu_mask_vk"))
        win32api.keybd_event(mask, 0, 0, 0)
        win32api.keybd_event(mask, 0, win32con.KEYEVENTF_KEYUP, 0)

    def _wait_release(self, vk: int):
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < self._release_timeout:
            if not (win32api.GetAsyncKeyState(vk) & 0x8000):
                return
            time.sleep(0.01)

    def run(self):
        info("hotkey watcher running")
        self._running = True
        was_pressed = False
        while self._running:
            vk = settings.hotkey_vk()
            pressed = bool(win32api.GetAsyncKeyState(vk) & 0x8000)
            if pressed and not was_pressed:
                if settings.get("hotkey.vk") in MENU_KEYS:
                    self._mask_menu()
                if not self.suspended:
                    self._wait_release(vk)
                    self._on_press()
            was_pressed = pressed
            time.sleep(self._interval)
