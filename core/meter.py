"""Standalone microphone level meter for onboarding — no engine involved."""
import threading

import numpy as np

from core.config import settings
from core.logger import error
from core.microphone import Microphone


def level_of(block: bytes) -> float:
    """Loudness 0..1 on a dBFS scale from audio.meter_floor_db up to 0 dB.

    Both meters (recording pill, onboarding) read this one scale and apply
    their own gate and gain to it.
    """
    samples = np.frombuffer(block, dtype=np.int16).astype(np.float32) / 32768.0
    db = 10.0 * np.log10(float(np.mean(samples * samples)) + 1e-10)
    return round(min(1.0, max(0.0, 1.0 - db / float(settings.get("audio.meter_floor_db")))), 3)


class Meter:
    def __init__(self, emit):
        self._emit = emit
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _run(self):
        mic = Microphone()
        try:
            mic.open()
        except Exception as exc:
            error(f"meter microphone open failed: {type(exc).__name__}: {exc}")
            self._emit("meter_error", {})
            return
        try:
            while not self._stop.is_set():
                block = mic.read_block()
                if block is None:
                    break
                self._emit("level", {"value": level_of(block)})
        finally:
            mic.close()
