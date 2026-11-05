"""User-managed hotword vocabulary (JSON backed).

Schema:
  {
    "version": 1,
    "hotwords": ["张茜", "启明计划", "李倩"]
  }

The engine consumes a flat newline-separated file, so this module renders the
JSON vocabulary to engine/hotwords.txt before every engine start. Users edit
only the JSON; the rendered file is generated.
"""
import json
from pathlib import Path

from core.config import CONFIG_DIR, settings
from core.logger import error, info, warn

HOTWORDS_JSON = CONFIG_DIR / "hotwords.json"
SCHEMA_VERSION = 1


class HotwordError(ValueError):
    """Rejected edit; args[0] is a machine-readable reason code."""


def load_hotwords() -> list[str]:
    if not HOTWORDS_JSON.exists():
        _save([])
        info(f"hotwords.json created at {HOTWORDS_JSON}")
        return []

    try:
        data = json.loads(HOTWORDS_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        error(f"hotwords.json invalid ({type(exc).__name__}: {exc}), using empty list")
        return []

    raw = data.get("hotwords", []) if isinstance(data, dict) else []
    words = []
    for item in raw:
        if not isinstance(item, str):
            warn(f"hotword entry ignored (not a string): {item!r}")
            continue
        word = item.strip()
        if word and word not in words:
            words.append(word)

    cap = int(settings.get("engine.hotword_max_count"))
    if len(words) > cap:
        warn(f"hotword count {len(words)} exceeds {cap}, truncating")
        words = words[:cap]
    return words


def _save(words: list[str]):
    HOTWORDS_JSON.parent.mkdir(parents=True, exist_ok=True)
    HOTWORDS_JSON.write_text(
        json.dumps({"version": SCHEMA_VERSION, "hotwords": words}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def _validate(word: str, others: list[str]) -> str:
    word = word.strip()
    if not word:
        raise HotwordError("empty")
    if len(word) > int(settings.get("engine.hotword_max_length")):
        raise HotwordError("too_long")
    if word in others:
        raise HotwordError("duplicate")
    return word


def add_hotword(word: str) -> list[str]:
    words = load_hotwords()
    if len(words) >= int(settings.get("engine.hotword_max_count")):
        raise HotwordError("full")
    words.insert(0, _validate(word, words))
    _save(words)
    info(f"hotword added: {words[0]}")
    return words


def update_hotword(old: str, new: str) -> list[str]:
    words = load_hotwords()
    if old not in words:
        raise HotwordError("missing")
    index = words.index(old)
    words[index] = _validate(new, words[:index] + words[index + 1:])
    _save(words)
    info(f"hotword edited: {old} -> {words[index]}")
    return words


def remove_hotword(word: str) -> list[str]:
    words = load_hotwords()
    if word in words:
        words.remove(word)
        _save(words)
        info(f"hotword deleted: {word}")
    return words


def render_for_engine() -> Path:
    """Write the flat file the engine expects. Returns its path."""
    target = settings.path("engine.hotwords_file")
    target.parent.mkdir(parents=True, exist_ok=True)
    words = load_hotwords()
    target.write_text("\n".join(words), encoding="utf-8")
    info(f"hotwords rendered: {len(words)} entries -> {target.name}")
    return target
