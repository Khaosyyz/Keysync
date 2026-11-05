"""KeySync entry point: hotkey toggles a session; the shell renders the UI."""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import settings
from core.logger import error, info


def main():
    info("=" * 50)
    info("KeySync starting")

    engine = settings.path("engine.exe")
    if not engine.exists():
        error(f"missing required file: {engine}")
        return 1

    from core.hotkey import HotkeyWatcher
    from core.session import Session
    from ui.app import Shell

    watcher = HotkeyWatcher(lambda: threading.Thread(target=session.toggle, daemon=True).start())
    shell = Shell(watcher)
    session = Session(shell.emit, shell.models)
    threading.Thread(target=watcher.run, daemon=True).start()

    info("KeySync ready")
    shell.run()

    watcher.stop()
    session.shutdown()
    info("KeySync stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
