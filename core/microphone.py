"""Microphone capture (16 kHz mono s16le)."""
import sounddevice as sd

from core.config import settings
from core.logger import info, warn


class Microphone:
    def __init__(self):
        self._stream = None
        self._rate = int(settings.get("audio.sample_rate", 16000))
        self._block = int(settings.get("audio.block_frames", 1600))
        self._channels = int(settings.get("audio.channels", 1))

    def open(self):
        device = settings.get("audio.device_name", "") or None
        index = self._resolve_device(device)
        self._stream = sd.InputStream(
            device=index, channels=self._channels, dtype="int16",
            samplerate=self._rate, blocksize=self._block)
        self._stream.start()
        name = sd.query_devices(index)["name"] if index is not None else sd.query_devices(sd.default.device[0])["name"]
        info(f"microphone open: {name} @ {self._rate}Hz")

    def _resolve_device(self, name):
        if not name:
            return sd.default.device[0]
        for index, device_name in _input_devices():
            if device_name == name:
                return index
        warn(f"configured microphone '{name}' not found, using default")
        return sd.default.device[0]

    def read_block(self) -> bytes | None:
        if self._stream is None:
            return None
        samples, overflowed = self._stream.read(self._block)
        if overflowed:
            warn("microphone buffer overflow")
        return samples.reshape(-1).tobytes()

    def close(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
            info("microphone closed")


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
