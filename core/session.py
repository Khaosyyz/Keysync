"""Session orchestration: hotkey toggle -> capture -> transcribe -> deliver -> record.

The --stream engine segments by audio time, so the feed rate must track real
time. To keep that invariant while the engine boots, capture and feeding are
decoupled by a single ordered queue drained by one feeder thread:

  capture thread -> queue (raw 100 ms blocks, in order)
  feeder thread  -> engine, paced to the wall clock of capture

When the engine is not ready yet the queue simply grows; the feeder starts
draining from the front the moment READY arrives, so ordering is preserved and
nothing is dropped or duplicated.

UI progress is reported through emit(event, payload):
  recording {} | level {value} | transcribing {} | result {record} | error {code}
"""
import queue
import threading
import time

from core.config import settings
from core.engine import Engine
from core.history_store import save_record
from core.meter import level_of
from core.logger import error, info, warn
from core.microphone import Microphone
from core.output_probe import FocusProbe
from core.output_sink import inject_text


class Session:
    def __init__(self, emit):
        self._emit = emit
        self._probe = FocusProbe()
        self._toggle_lock = threading.Lock()
        self._mic = None
        self._engine = None
        self._active = False
        self._probe_result = None
        self._pcm = []

        self._audio_q = queue.Queue()
        self._boot_done = threading.Event()
        self._feeder_done = threading.Event()

    def shutdown(self):
        if self._engine is not None:
            self._engine.shutdown()

    def toggle(self):
        if not self._toggle_lock.acquire(blocking=False):
            info("previous session still finalizing, press ignored")
            return
        try:
            if not self._active:
                self._begin()
            else:
                self._end()
        except Exception as exc:
            error(f"session failed: {type(exc).__name__}: {exc}")
            self._active = False
            self._emit("error", {"code": "internal"})
        finally:
            self._toggle_lock.release()

    def _begin(self):
        self._active = True
        self._probe_result = None
        self._pcm = []
        self._engine = None
        self._audio_q = queue.Queue()
        self._boot_done.clear()
        self._feeder_done.clear()

        threading.Thread(target=self._probe_async, daemon=True).start()
        threading.Thread(target=self._boot_engine, daemon=True).start()

        self._mic = Microphone()
        try:
            self._mic.open()
        except Exception as exc:
            error(f"microphone open failed: {type(exc).__name__}: {exc}")
            self._active = False
            self._audio_q.put(None)
            self._emit("error", {"code": "microphone"})
            return

        threading.Thread(target=self._capture_loop, daemon=True).start()
        self._emit("recording", {})
        info("session started (capturing)")

    def _probe_async(self):
        try:
            self._probe_result = self._probe.probe()
            info(f"focus probe: {self._probe_result}")
        except Exception as exc:
            error(f"probe failed: {type(exc).__name__}: {exc}")

    def _boot_engine(self):
        engine = Engine()
        try:
            t0 = time.perf_counter()
            engine.start()
            if not engine.wait_ready():
                error("engine failed to become ready")
                engine.shutdown()
                return
            info(f"engine ready in {time.perf_counter() - t0:.2f}s")
            self._engine = engine
            threading.Thread(target=self._feed_loop, args=(engine,), daemon=True).start()
        except Exception as exc:
            error(f"engine start failed: {type(exc).__name__}: {exc}")
        finally:
            self._boot_done.set()

    def _capture_loop(self):
        while self._active:
            try:
                block = self._mic.read_block()
            except Exception as exc:
                error(f"microphone read failed: {type(exc).__name__}: {exc}")
                return
            if block is None:
                return
            self._pcm.append(block)
            self._audio_q.put((time.perf_counter(), block))
            self._emit("level", {"value": level_of(block)})

    def _feed_loop(self, engine):
        """Drain the queue in order, paced against the capture timestamps."""
        first_ts = None
        try:
            while True:
                item = self._audio_q.get()
                if item is None:
                    return
                ts, block = item
                if first_ts is None:
                    first_ts = ts
                wait = (ts - first_ts) - (time.perf_counter() - first_ts)
                if wait > 0:
                    time.sleep(min(wait, 1.0))
                engine.feed(block)
        finally:
            self._feeder_done.set()

    def _end(self):
        self._active = False
        if self._mic is not None:
            self._mic.close()
        info("capture stopped")
        self._emit("transcribing", {})

        self._boot_done.wait(timeout=float(settings.get("engine.startup_timeout_s")))
        engine = self._engine
        if engine is None:
            error("engine unavailable, nothing to transcribe")
            self._emit("error", {"code": "engine"})
            return

        self._audio_q.put(None)
        deadline = float(settings.get("session.finalize_timeout_s"))
        if not self._feeder_done.wait(timeout=deadline):
            warn(f"feeder did not finish within {deadline}s")

        t0 = time.perf_counter()
        text = engine.stop_and_collect().strip()
        finalize_s = time.perf_counter() - t0
        engine.shutdown()
        self._engine = None
        info(f"transcript {len(text)} chars, finalize {finalize_s:.2f}s")

        result = self._probe_result
        if len(text) < int(settings.get("session.min_inject_chars")):
            delivery = "none"
            warn("transcript empty, nothing delivered")
        elif result is not None and result.can_input and inject_text(text):
            delivery = "typed"
            info(f"delivered by injection: {text[:40]}")
        else:
            delivery = "shown"
            info(f"not injected ({result.reason if result else 'probe unavailable'}), showing result")

        self._emit("result", {"record": save_record(b"".join(self._pcm), text, delivery)})
