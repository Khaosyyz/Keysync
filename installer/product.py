"""Product identity and its footprint in Windows, shared by the installer and uninstaller."""
import ctypes
import os
import winreg
from pathlib import Path

from win32com.client import Dispatch
from win32com.shell import shell, shellcon

NAME = "KeySync"
VERSION = "0.1.0"
PUBLISHER = "KeySync"
APP_EXE = "KeySync.exe"
UNINSTALL_EXE = "Uninstall.exe"
APP_FILES = (APP_EXE, "_internal", "engine")
PROGRAM = (*APP_FILES, UNINSTALL_EXE)
PAYLOAD = "payload.zip"
DEFAULT_DIR = Path(os.environ.get("SystemDrive", "C:") + "\\") / NAME
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{NAME}"
CHINESE_LANGID = 0x04


def ui_language() -> str:
    primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
    return "zh" if primary == CHINESE_LANGID else "en"


def shortcuts() -> list[Path]:
    folders = (shellcon.CSIDL_DESKTOPDIRECTORY, shellcon.CSIDL_PROGRAMS)
    return [Path(shell.SHGetFolderPath(0, folder, 0, 0)) / f"{NAME}.lnk" for folder in folders]


def create_shortcuts(target: Path):
    wsh = Dispatch("WScript.Shell")
    for path in shortcuts():
        link = wsh.CreateShortcut(str(path))
        link.TargetPath = str(target)
        link.WorkingDirectory = str(target.parent)
        link.IconLocation = f"{target},0"
        link.Save()


def is_running(directory: Path) -> bool:
    try:
        (directory / APP_EXE).open("r+b").close()
    except PermissionError:
        return True
    except FileNotFoundError:
        pass
    return False


def installed_dir() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            return Path(winreg.QueryValueEx(key, "InstallLocation")[0])
    except OSError:
        return None
