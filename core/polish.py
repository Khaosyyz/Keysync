"""Post-processing stage between local transcription and delivery.

The cloud pass is not wired up yet: polish() is a simulated pass that keeps the
text unchanged after a fixed delay, so the pipeline stage and its progress event
are already in place. The stage is announced with emit("polishing").
"""
import time

from core.config import settings
from core.logger import info


def polish(text: str) -> str:
    delay = float(settings.get("polish.simulate_delay_s"))
    time.sleep(delay)
    info(f"polish: simulated pass, {delay:.1f}s")
    return text
