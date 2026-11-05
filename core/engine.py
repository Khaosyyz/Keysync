"""Engine subprocess: lifecycle, PCM feeding, line-protocol parsing.

Protocol (from the official llama-funasr-cli --stream):
  READY              engine loaded and waiting for PCM
  PARTIAL <text>     in-progress preview (display only, never injected)
  PARTIAL            preview cleared
  LOCKED <text>      finalized segment (this is what we collect)
  DONE               emitted after stdin EOF and trailing decode
stdin: raw 16 kHz mono s16le PCM.

Offline mode (-a file.wav) prints the full transcript on stdout.
"""
import os
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

import soundfile as sf

from core.config import settings
from core.hotwords import render_for_engine
from core.logger import error, info, warn


def _command(*mode) -> list[str]:
    return [
        str(settings.path("engine.exe")),
        "--enc", str(settings.path("engine.encoder_model")),
        "-m", str(settings.path("engine.llm_model")),
        "--vad", str(settings.path("engine.vad_model")),
        "--vad-maxseg", str(settings.get("engine.vad_max_segment_ms")),
        "-n", str(settings.get("engine.max_new_tokens")),
        "--rep", str(settings.get("engine.repetition_penalty")),
        "--lang", str(settings.get("engine.language")),
        "--hotwords-file", str(render_for_engine()),
        *mode,
    ]


def transcribe_file(audio: Path) -> str:
    """Offline transcription of a stored recording; the engine reads WAV only,
    so anything else is decoded to a temp WAV first."""
    data, rate = sf.read(str(audio), dtype="int16")
    fd, wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        with wave.open(wav, "wb") as out:
            out.setnchannels(1 if data.ndim == 1 else data.shape[1])
            out.setsampwidth(2)
            out.setframerate(rate)
            out.writeframes(data.tobytes())
        cmd = _command("-a", wav)
        info(f"engine offline: {audio.name}")
        result = subprocess.run(
            cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=float(settings.get("engine.transcribe_timeout_s")))
        if result.returncode != 0:
            raise RuntimeError(f"engine exited with code {result.returncode}")
        return result.stdout.decode("utf-8", errors="replace").strip()
    finally:
        os.unlink(wav)


class Engine:
    def __init__(self):
        self._proc = None
        self._ready = threading.Event()
        self._done = threading.Event()
        self._lock = threading.Lock()
        self._locked = []

    def start(self):
        cmd = _command("--stream")
        info(f"engine start: {' '.join(cmd)}")
        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0,
            creationflags=subprocess.CREATE_NO_WINDOW)
        threading.Thread(target=self._read_loop, daemon=True).start()

    def wait_ready(self) -> bool:
        timeout = float(settings.get("engine.startup_timeout_s"))
        ok = self._ready.wait(timeout)
        if not ok:
            error(f"engine did not become ready within {timeout}s")
        return ok

    def _read_loop(self):
        for raw in self._proc.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            tag, _, body = line.partition(" ")
            if tag == "READY":
                self._ready.set()
                info("engine ready")
            elif tag == "PARTIAL":
                pass
            elif tag == "LOCKED":
                with self._lock:
                    self._locked.append(body)
                info(f"locked: {body[:60]}")
            elif tag == "DONE":
                self._done.set()
                info("engine done")
            elif tag == "DEBUG":
                pass
            else:
                warn(f"engine output: {line[:120]}")
        info("engine stdout closed")

    def feed(self, pcm_bytes: bytes):
        if self._proc is None or self._proc.stdin is None:
            return
        try:
            self._proc.stdin.write(pcm_bytes)
            self._proc.stdin.flush()
        except Exception as exc:
            error(f"engine feed failed: {type(exc).__name__}: {exc}")

    def stop_and_collect(self) -> str:
        """Close stdin, wait for the engine to finish the trailing segment.

        Keeps every LOCKED segment collected during this session — including any
        that were emitted before the stop was requested.
        """
        self._done.clear()
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
        except Exception:
            pass
        timeout = float(settings.get("engine.shutdown_timeout_s"))
        if not self._done.wait(timeout):
            warn(f"engine DONE not received within {timeout}s")
        with self._lock:
            return "".join(self._locked)

    def shutdown(self):
        if self._proc is None:
            return
        try:
            if self._proc.stdin and not self._proc.stdin.closed:
                self._proc.stdin.close()
        except Exception:
            pass
        try:
            self._proc.wait(timeout=float(settings.get("engine.shutdown_timeout_s")))
        except Exception:
            self._proc.kill()
        info("engine shutdown")
