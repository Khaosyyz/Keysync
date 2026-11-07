"""Microphone capture (16 kHz mono s16le), opened per recording.

activate() is the first thing the hotkey path does - the engine and the focus
probe start only after the stream is up, so nothing competes with the open.
close() ends the stream with the session; between sessions no capture exists.
"""
import threading

import sounddevice as sd

from core.config import settings
from core.logger import error, info, warn


class Microphone:
    def __init__(self):
        self.on_block = None
        self._stream = None
        self._lock = threading.Lock()
        self._rate = int(settings.get("audio.sample_rate"))
        self._block = int(settings.get("audio.block_frames"))
        self._channels = int(settings.get("audio.channels"))

    def activate(self) -> bool:
        with self._lock:
            if self._stream is not None:
                return True
        try:
            stream, name = self._open()
        except Exception as exc:
            error(f"microphone open failed: {type(exc).__name__}: {exc}")
            return False
        with self._lock:
            self._stream = stream
        threading.Thread(target=self._read_loop, args=(stream,), daemon=True).start()
        info(f"microphone open: {name} @ {self._rate}Hz")
        return True

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
        index = self._resolve_device()
        name = str(sd.query_devices(index)["name"]).strip()
        stream = sd.InputStream(
            device=index, channels=self._channels, dtype="int16",
            samplerate=self._rate, blocksize=self._block)
        stream.start()
        return stream, name

    def _read_loop(self, stream):
        while self._stream is stream:
            try:
                samples, overflowed = stream.read(self._block)
            except Exception:
                return
            if overflowed:
                warn("microphone buffer overflow")
            self.on_block(samples.reshape(-1).tobytes())

    def _resolve_device(self):
        name = settings.get("audio.device_name")
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
