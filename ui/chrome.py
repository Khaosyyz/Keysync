"""Native title bar: coloured to match the page beneath it, without icon or caption text."""
import ctypes

_dwm_set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
_dwm_set_attribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
_set_theme_attribute = ctypes.windll.uxtheme.SetWindowThemeAttribute
_set_theme_attribute.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
WTA_NONCLIENT = 1
WTNCA_NODRAWCAPTION = 0x1
WTNCA_NODRAWICON = 0x2


class _WTA_OPTIONS(ctypes.Structure):
    _fields_ = [("dwFlags", ctypes.c_uint), ("dwMask", ctypes.c_uint)]


def hwnd_of(window) -> int:
    return window.native.Handle.ToInt32()


def _dwm_set(hwnd: int, attr: int, value: int):
    v = ctypes.c_uint(value)
    _dwm_set_attribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))


def hide_caption(hwnd: int):
    flags = WTNCA_NODRAWCAPTION | WTNCA_NODRAWICON
    opts = _WTA_OPTIONS(flags, flags)
    _set_theme_attribute(hwnd, WTA_NONCLIENT, ctypes.byref(opts), ctypes.sizeof(opts))


def paint_caption(hwnd: int, rgb: list[int], dark: bool):
    r, g, b = rgb
    colorref = r | (g << 8) | (b << 16)
    _dwm_set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, int(dark))
    _dwm_set(hwnd, DWMWA_CAPTION_COLOR, colorref)
    _dwm_set(hwnd, DWMWA_BORDER_COLOR, colorref)
