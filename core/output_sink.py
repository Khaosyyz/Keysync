"""Delivery of the finished transcript.

inject_text pastes atomically: the text goes on the clipboard as
CF_UNICODETEXT, a synthetic Ctrl+V lands it in the focused window in one shot,
and the user's previous clipboard text is restored shortly after. Typing the
text as key events is not an option - with long transcripts, char-by-char
unicode events get dropped and mangled by the receiving app.
"""
import threading
import time

import pynput.keyboard as pk
import win32clipboard

from core.logger import error

_restore_timer = None


def _clipboard_text():
    try:
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            return None
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return None


def _set_clipboard_text(text):
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()


def inject_text(text: str) -> bool:
    global _restore_timer
    try:
        previous = _clipboard_text()
        _set_clipboard_text(text)
        controller = pk.Controller()
        with controller.pressed(pk.Key.ctrl):
            controller.press("v")
            time.sleep(0.02)
            controller.release("v")
        if previous is not None and previous != text:
            _restore_timer = threading.Timer(0.4, _set_clipboard_text, args=(previous,))
            _restore_timer.start()
        return True
    except Exception as exc:
        error(f"inject_text failed: {type(exc).__name__}: {exc}")
        return False


def copy_text(text: str):
    _set_clipboard_text(text)
