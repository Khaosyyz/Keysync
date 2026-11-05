"""Uninstaller, run from inside the install folder.

The folder is removed whole (it belongs to KeySync alone, see install.py). A
running exe cannot delete itself, so a hidden PowerShell waits for this process
to exit and then removes the folder. PowerShell needs a console of its own, so
it gets a hidden one (CREATE_NO_WINDOW); a detached process would not run.
"""
import ctypes
import os
import subprocess
import sys
import winreg
from pathlib import Path

from installer import product

MB_YESNO = 0x4
MB_ICONWARNING = 0x30
MB_ICONINFORMATION = 0x40
IDYES = 6

TEXT = {
    "zh": {
        "confirm": "确定要卸载 KeySync 吗？\n\n安装目录中的录音历史、设置和已下载的语音模型也会一并删除。",
        "running": "KeySync 正在运行，请先退出后再卸载。",
        "done": "KeySync 已卸载。",
    },
    "en": {
        "confirm": "Uninstall KeySync?\n\nRecordings, settings and downloaded speech models in the install folder will be deleted too.",
        "running": "KeySync is running. Quit it first, then uninstall.",
        "done": "KeySync has been uninstalled.",
    },
}


def _message(text: str, flags: int) -> int:
    return ctypes.windll.user32.MessageBoxW(None, text, f"{product.NAME} {product.VERSION}", flags)


def _remove_later(directory: Path):
    quoted = str(directory).replace("'", "''")
    script = f"Wait-Process -Id {os.getppid()} -ErrorAction SilentlyContinue; Remove-Item -LiteralPath '{quoted}' -Recurse -Force"
    subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                     creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)


def main():
    directory = Path(sys.executable).resolve().parent
    if not (directory / product.APP_EXE).exists():
        return 1
    text = TEXT[product.ui_language()]
    if _message(text["confirm"], MB_YESNO | MB_ICONWARNING) != IDYES:
        return 0
    if product.is_running(directory):
        _message(text["running"], MB_ICONWARNING)
        return 1
    for link in product.shortcuts():
        link.unlink(missing_ok=True)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, product.UNINSTALL_KEY)
    except FileNotFoundError:
        pass
    _remove_later(directory)
    _message(text["done"], MB_ICONINFORMATION)
    return 0


if __name__ == "__main__":
    sys.exit(main())
