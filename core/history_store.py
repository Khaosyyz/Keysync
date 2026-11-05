"""Transcription history: one WAV + one JSON per session, grouped by day.

  data/20261105/20261105-143025123.wav
  data/20261105/20261105-143025123.json   {id, timestamp, text, duration_s, delivery}

Day folders older than history.retention_days are purged on load.
"""
import json
import re
import shutil
import wave
from datetime import datetime, timedelta
from pathlib import Path

from core.config import settings

_ID = re.compile(r"^\d{8}-\d{9}$")


def _root() -> Path:
    return settings.path("history.dir")


def _paths(entry_id: str) -> tuple[Path, Path]:
    if not _ID.match(entry_id):
        raise ValueError(f"invalid history id: {entry_id!r}")
    day = _root() / entry_id[:8]
    return day / f"{entry_id}.json", day / f"{entry_id}.wav"


def _write_meta(path: Path, meta: dict):
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def save_record(pcm: bytes, text: str, delivery: str) -> dict:
    now = datetime.now()
    entry_id = now.strftime("%Y%m%d-%H%M%S") + f"{now.microsecond // 1000:03d}"
    meta_path, wav_path = _paths(entry_id)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    rate = int(settings.get("audio.sample_rate"))
    channels = int(settings.get("audio.channels"))
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)

    meta = {
        "id": entry_id,
        "timestamp": now.isoformat(timespec="seconds"),
        "text": text,
        "duration_s": round(len(pcm) / (2 * channels * rate), 1),
        "delivery": delivery,
    }
    _write_meta(meta_path, meta)
    return meta


def load_history() -> list[dict]:
    root = _root()
    if not root.exists():
        return []
    cutoff = (datetime.now() - timedelta(days=int(settings.get("history.retention_days")))).strftime("%Y%m%d")
    entries = []
    for day in root.iterdir():
        if not day.is_dir() or not day.name.isdigit():
            continue
        if day.name < cutoff:
            shutil.rmtree(day, ignore_errors=True)
            continue
        for meta_file in day.glob("*.json"):
            try:
                entries.append(json.loads(meta_file.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    entries.sort(key=lambda e: e["id"], reverse=True)
    return entries


def audio_path(entry_id: str) -> Path:
    return _paths(entry_id)[1]


def update_text(entry_id: str, text: str) -> dict:
    meta_path, _ = _paths(entry_id)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["text"] = text
    _write_meta(meta_path, meta)
    return meta


def delete_record(entry_id: str):
    meta_path, wav_path = _paths(entry_id)
    meta_path.unlink(missing_ok=True)
    wav_path.unlink(missing_ok=True)
    day = meta_path.parent
    if day.exists() and not any(day.iterdir()):
        day.rmdir()
