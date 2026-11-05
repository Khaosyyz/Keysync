"""Delivery of the finished transcript.

  injectable  -> keyboard.write(full text) in one shot
  otherwise   -> the UI shows the text; the clipboard is touched only when the
                 user presses a copy button (copy_text)
"""
import keyboard
import win32clipboard

from core.config import settings
from core.logger import error


def inject_text(text: str) -> bool:
    try:
        keyboard.write(text, delay=float(settings.get("output.char_delay_ms")) / 1000.0)
        return True
    except Exception as exc:
        error(f"inject_text failed: {type(exc).__name__}: {exc}")
        return False


def copy_text(text: str):
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()
