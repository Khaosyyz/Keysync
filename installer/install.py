"""Setup: unpacks the bundled program into a folder the user picks.

The folder belongs to KeySync alone: it must be empty or an earlier install,
which is what lets the uninstaller remove it whole. Upgrading replaces only the
program; config, history and models beside it are kept. Everything is per user
(no elevation): shortcuts and the Apps & Features entry live under HKCU.
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import winreg
import zipfile
from pathlib import Path

import webview

from installer import product
from ui.chrome import hide_caption, hwnd_of, paint_caption

RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
WEB_DIR = RESOURCE_DIR / "ui" / "web"
WINDOW_SIZE = (560, 420)
PROGRESS_INTERVAL_S = 0.05


class SetupError(Exception):
    pass


def _check_target(target: Path):
    if not target.is_absolute() or target.is_file():
        raise SetupError("invalid")
    if target.is_dir() and any(target.iterdir()) and not (target / product.APP_EXE).exists():
        raise SetupError("occupied")
    if product.is_running(target):
        raise SetupError("running")
    try:
        target.mkdir(parents=True, exist_ok=True)
        tempfile.TemporaryFile(dir=target).close()
    except PermissionError:
        raise SetupError("denied")
    except OSError:
        raise SetupError("invalid")


def _register(target: Path, size_kb: int):
    exe = target / product.APP_EXE
    values = {
        "DisplayName": product.NAME,
        "DisplayVersion": product.VERSION,
        "Publisher": product.PUBLISHER,
        "DisplayIcon": str(exe),
        "InstallLocation": str(target),
        "UninstallString": f'"{target / product.UNINSTALL_EXE}"',
    }
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, product.UNINSTALL_KEY) as key:
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
        for name in ("NoModify", "NoRepair"):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)


class SetupApi:
    def __init__(self):
        self.window = None
        self.busy = False
        self._target = None
        self._published = 0.0

    def _emit(self, event: str, payload: dict):
        detail = json.dumps(payload)
        self.window.evaluate_js(f"window.dispatchEvent(new CustomEvent('ks:{event}', {{detail: {detail}}}))")

    def bootstrap(self):
        return {"language": product.ui_language(), "dir": str(product.installed_dir() or product.DEFAULT_DIR)}

    def ready(self):
        hide_caption(hwnd_of(self.window))
        self.window.show()

    def set_chrome(self, caption: list[int], dark: bool):
        paint_caption(hwnd_of(self.window), caption, dark)

    def browse(self, current: str):
        start = Path(current).parent if Path(current).parent.is_dir() else product.DEFAULT_DIR.parent
        picked = self.window.create_file_dialog(webview.FileDialog.FOLDER, directory=str(start))
        if not picked:
            return None
        folder = Path(picked[0])
        return str(folder if folder.name.lower() == product.NAME.lower() else folder / product.NAME)

    def install(self, path: str):
        target = Path(path.strip().strip('"'))
        _check_target(target)
        self.busy = True
        threading.Thread(target=self._install, args=(target,), daemon=True).start()

    def _progress(self, done: int, total: int):
        if time.monotonic() - self._published >= PROGRESS_INTERVAL_S or done == total:
            self._published = time.monotonic()
            self._emit("progress", {"value": done / total})

    def _install(self, target: Path):
        try:
            for name in product.PROGRAM:
                old = target / name
                if old.is_dir():
                    shutil.rmtree(old)
                else:
                    old.unlink(missing_ok=True)
            with zipfile.ZipFile(RESOURCE_DIR / product.PAYLOAD) as payload:
                entries = payload.infolist()
                total = sum(e.file_size for e in entries)
                done = 0
                for entry in entries:
                    payload.extract(entry, target)
                    done += entry.file_size
                    self._progress(done, total)
            product.create_shortcuts(target / product.APP_EXE)
            _register(target, total // 1024)
            self._target = target
            self._emit("done", {})
        except Exception:
            self._emit("failed", {})
        finally:
            self.busy = False

    def launch(self):
        os.startfile(self._target / product.APP_EXE)
        self.window.destroy()


def main():
    api = SetupApi()
    api.window = webview.create_window(
        f"{product.NAME} Setup", str(WEB_DIR / "setup.html"), js_api=api,
        width=WINDOW_SIZE[0], height=WINDOW_SIZE[1], resizable=False, hidden=True)
    api.window.events.closing += lambda: not api.busy
    webview.start(gui="edgechromium", private_mode=True)


if __name__ == "__main__":
    main()
