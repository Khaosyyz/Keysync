"""Unified logging with rotation-free append and console mirroring."""
import threading
from datetime import datetime

from core.config import LOGS_DIR, settings

_LOCK = threading.Lock()
_LOG_FILE = None


def _ensure_file():
    global _LOG_FILE
    if _LOG_FILE is None:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        _LOG_FILE = LOGS_DIR / f"keysync-{datetime.now():%Y%m%d}.log"
    return _LOG_FILE


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] [{level}] {msg}"
    with _LOCK:
        try:
            with open(_ensure_file(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
    if settings.get("logging.console", True):
        print(line, flush=True)


def info(msg):
    log(msg, "INFO")


def warn(msg):
    log(msg, "WARN")


def error(msg):
    log(msg, "ERROR")
