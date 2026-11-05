"""Microphone capture (16 kHz mono s16le) with a hot standby stream.

Opening a stream makes the device click and costs a few hundred milliseconds,
so the stream stays open from app start: while idle a reader thread keeps a
short pre-roll ring, and a hotkey press replays those samples into the session
and switches the same stream to live capture. Nothing is lost to device
startup, and the click never lands inside a recording.
"""
import threading
from collections import deque

import sounddevice as sd

from core.config import settings
from core.logger import error, info, warn


class Microphone:
    def __init__(self):
        self.on_block = None
        self._stream = None
        self._lock = threading.Lock()
        self._active = False
        self._pre_roll = None
        self._rate = int(settings.get("audio.sample_rate"))
        self._block = int(settings.get("audio.block_frames"))
        self._channels = int(settings.get("audio.channels"))
        self._pre_blocks = max(1, round(float(settings.get("audio.pre_roll_s")) * self._rate / self._block))

    def prime(self):
        """Open the standby stream; activate() retries if no device was ready yet."""
        try:
            self._open()
        except Exception as exc:
            warn(f"microphone standby unavailable: {type(exc).__name__}: {exc}")

    def activate(self) -> list[bytes] | None:
        """Standby -> live. Returns the pre-roll (oldest first), or None if no mic."""
        try:
            self._open()
        except Exception as exc:
            error(f"microphone open failed: {type(exc).__name__}: {exc}")
            return None
        with self._lock:
            self._active = True
            pre = list(self._pre_roll)
            self._pre_roll.clear()
            return pre

    def standby(self):
        with self._lock:
            self._active = False
            if self._pre_roll is not None:
                self._pre_roll.clear()

    def close(self):
        with self._lock:
            stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            info("microphone closed")

    def _open(self):
        if self._stream is not None:
            return
        device = settings.get("audio.device_name") or None
        index = self._resolve_device(device)
        self._stream = sd.InputStream(
            device=index, channels=self._channels, dtype="int16",
            samplerate=self._rate, blocksize=self._block)
        self._stream.start()
        self._pre_roll = deque(maxlen=self._pre_blocks)
        threading.Thread(target=self._read_loop, daemon=True).start()
        name = sd.query_devices(index)["name"] if index is not None else sd.query_devices(sd.default.device[0])["name"]
        info(f"microphone open: {name} @ {self._rate}Hz (standby)")

    def _read_loop(self):
        while self._stream is not None:
            try:
                samples, overflowed = self._stream.read(self._block)
            except Exception:
                with self._lock:
                    self._stream = None
                return
            if overflowed:
                warn("microphone buffer overflow")
            block = samples.reshape(-1).tobytes()
            with self._lock:
                if self._active:
                    self.on_block(block)
                else:
                    self._pre_roll.append(block)

    def _resolve_device(self, name):
        if not name:
            return sd.default.device[0]
        for index, device_name in _input_devices():
            if device_name == name:
                return index
        warn(f"configured microphone '{name}' not found, using default")
        return sd.default.device[0]


def _input_devices() -> list[tuple[int, str]]:
    """Inputs of the host API that owns the default input (the one capture uses).

    Every physical mic appears once per host API (MME, DirectSound, WDM-KS...);
    listing a single API removes those duplicates and keeps the chosen name
    resolvable to the same stream the session opens.
    """
    try:
        host = sd.query_devices(sd.default.device[0])["hostapi"]
    except (sd.PortAudioError, ValueError):
        return []
    devices, seen = [], set()
    for index, d in enumerate(sd.query_devices()):
        name = str(d["name"]).strip()
        if d["hostapi"] == host and d["max_input_channels"] > 0 and name and name not in seen:
            seen.add(name)
            devices.append((index, name))
    return devices


def list_input_names() -> list[str]:
    return [name for _, name in _input_devices()]


def default_input_name() -> str:
    try:
        return str(sd.query_devices(sd.default.device[0])["name"]).strip()
    except (sd.PortAudioError, ValueError):
        return ""
