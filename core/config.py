"""Configuration center - every tunable value lives here, nothing hardcoded elsewhere.

Defaults live in DEFAULT_CONFIG; config/config.json holds only what the user
changed, so a new default reaches existing installs. Modules read settings via
`settings.get("section.key")`.
"""
import json
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
CONFIG_DIR = BASE_DIR / "config"
LOGS_DIR = BASE_DIR / "logs"

CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "hotkey": {
        "vk": "AltRight",
        "poll_interval_ms": 20,
        "release_timeout_ms": 2000,
        "menu_mask_vk": 0xE8,
    },
    "audio": {
        "device_name": "",
        "sample_rate": 16000,
        "block_frames": 800,
        "channels": 1,
        "meter_floor_db": -60,
        "pre_roll_s": 1.0,
    },
    "engine": {
        "exe": "engine/llama-funasr-cli.exe",
        "encoder_model": "models/funasr-encoder-f16.gguf",
        "llm_model": "models/qwen3-0.6b-q8_0.gguf",
        "vad_model": "models/fsmn-vad.gguf",
        "vad_max_segment_ms": 30000,
        "max_new_tokens": 512,
        "repetition_penalty": 1.0,
        "language": "Chinese",
        "startup_timeout_s": 60,
        "shutdown_timeout_s": 10,
        "transcribe_timeout_s": 120,
        "hotwords_file": "engine/hotwords.txt",
        "hotword_max_count": 200,
        "hotword_max_length": 10,
    },
    "models": {
        "name": "Fun-ASR-Nano",
        "repos": {
            "encoder_model": "FunAudioLLM/Fun-ASR-Nano-GGUF",
            "llm_model": "FunAudioLLM/Fun-ASR-Nano-GGUF",
            "vad_model": "FunAudioLLM/fsmn-vad-GGUF",
        },
        "manifest_url": "https://modelscope.cn/api/v1/models/{repo}/repo/files?Recursive=true",
        "file_url": "https://modelscope.cn/models/{repo}/resolve/master/{path}",
        "timeout_s": 30,
        "chunk_kb": 1024,
        "progress_interval_ms": 200,
    },
    "session": {
        "finalize_timeout_s": 10,
        "min_inject_chars": 1,
    },
    "output": {
        "char_delay_ms": 0,
        "probe_settle_ms": 150,
    },
    "history": {
        "dir": "data",
        "retention_days": 30,
        "write_chunk_s": 5,
    },
    "onboarding": {
        "completed": False,
    },
    "ui": {
        "theme": "system",
        "language": "en",
        "window_width": 1080,
        "window_height": 720,
        "window_min_width": 760,
        "window_min_height": 520,
        "overlay_bottom_margin_px": 12,
        "overlay_result_duration_s": 12,
        "overlay_notice_duration_s": 4,
        "overlay_delivered_duration_s": 0.5,
    },
    "logging": {
        "level": "info",
        "console": True,
    },
}

HOTKEY_VK = {
    "AltRight": 0xA5, "AltLeft": 0xA4,
    "ControlRight": 0xA3, "ControlLeft": 0xA2,
    "ShiftRight": 0xA1, "CapsLock": 0x14,
    "Insert": 0x2D, "Pause": 0x13, "ScrollLock": 0x91,
    **{f"F{i}": 0x6F + i for i in range(1, 13)},
}
MENU_KEYS = {"AltRight", "AltLeft"}


class Settings:
    def __init__(self):
        self._overrides = {}
        self._data = {}
        self.load()

    def load(self):
        try:
            self._overrides = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._overrides = {}
        self._data = _deep_merge(DEFAULT_CONFIG, self._overrides)

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(self._overrides, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, dotted_key, default=None):
        node = self._data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted_key, value):
        parts = dotted_key.split(".")
        for root in (self._overrides, self._data):
            node = root
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
        self.save()

    def hotkey_vk(self):
        return HOTKEY_VK.get(self.get("hotkey.vk"), HOTKEY_VK[DEFAULT_CONFIG["hotkey"]["vk"]])

    def path(self, dotted_key):
        raw = self.get(dotted_key, "")
        p = Path(raw)
        return p if p.is_absolute() else BASE_DIR / p


def _deep_merge(base, override):
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


settings = Settings()
