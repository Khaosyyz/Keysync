"""KeySync entry point: hotkey toggles a session; the shell renders the UI.

Background-first: closing the window hides it to the tray; the process lives
in the tray until Quit is chosen there. A second launch just refuses to start.
"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import win32api
import win32event
import winerror

from core.config import INSTANCE_MUTEX, settings
from core.logger import error, info

_instance_mutex = None


def _single_instance() -> bool:
    global _instance_mutex
    _instance_mutex = win32event.CreateMutex(None, False, INSTANCE_MUTEX)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        win32api.MessageBox(0, "KeySync is already running.", "KeySync")
        return False
    return True


def main():
    if not _single_instance():
        return 1
    info("=" * 50)
    info("KeySync starting")

    engine = settings.path("engine.exe")
    if not engine.exists():
        error(f"missing required file: {engine}")
        return 1

    from core.hotkey import HotkeyWatcher
    from core.microphone import Microphone
    from core.session import Session
    from ui.app import Shell

    watcher = HotkeyWatcher(lambda: threading.Thread(target=session.toggle, daemon=True).start())
    shell = Shell(watcher)
    mic = Microphone()
    session = Session(shell.emit, shell.models, mic)
    threading.Thread(target=watcher.run, daemon=True).start()

    info("KeySync ready")
    shell.run()

    watcher.stop()
    session.shutdown()
    info("KeySync stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
