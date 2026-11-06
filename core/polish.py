"""Cloud post-processing: provider request formats + the polish session stage.

The session stage (polish()) is still a simulated pass; request()/test_connection()
are the real provider layer the settings page drives, and will replace the
simulation once the stage is wired to the cloud.

Wire formats (verified against the official docs):
  openai    POST {base}/chat/completions   Authorization: Bearer <key>
  gemini    POST {base}/models/{model}:generateContent   x-goog-api-key: <key>
  anthropic POST {base}/v1/messages   x-api-key: <key>, anthropic-version: 2023-06-01
"""
import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from core.config import VERSION, settings
from core.logger import info, warn

TIMEOUT_S = 15


def _openai(base, key, model, system, text, max_tokens):
    url = f"{base}/chat/completions"
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}]}
    headers = {"Authorization": f"Bearer {key}"}

    def extract(r):
        message = r["choices"][0]["message"]
        return message["content"] or message.get("reasoning_content", "")
    return url, body, headers, extract


def _gemini(base, key, model, system, text, max_tokens):
    url = f"{base}/models/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": text}]}],
            "system_instruction": {"parts": [{"text": system}]},
            "generationConfig": {"maxOutputTokens": max_tokens}}
    headers = {"x-goog-api-key": key}
    return url, body, headers, lambda r: r["candidates"][0]["content"]["parts"][0]["text"]


def _anthropic(base, key, model, system, text, max_tokens):
    url = f"{base}/v1/messages"
    body = {"model": model, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": text}]}
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    return url, body, headers, lambda r: "".join(part.get("text", "") for part in r["content"])


BUILDERS = {"openai": _openai, "gemini": _gemini, "anthropic": _anthropic}
DEFAULT_BASES = {"openai": "https://api.openai.com/v1",
                 "gemini": "https://generativelanguage.googleapis.com/v1beta",
                 "anthropic": "https://api.anthropic.com"}
VERSION_PATHS = {"openai": "/v1", "gemini": "/v1beta", "anthropic": ""}
ENDPOINTS = {"openai": "/chat/completions", "gemini": ":generateContent", "anthropic": "/v1/messages"}


def _base(fmt: str, baseurl: str) -> str:
    """Bare domains get the provider's version path appended (relay convention):
    https://my-relay.com -> https://my-relay.com/v1/chat/completions. Pasting the
    full endpoint also works - the trailing endpoint part is stripped first."""
    base = (baseurl or DEFAULT_BASES[fmt]).rstrip("/")
    if base.endswith(ENDPOINTS[fmt]):
        base = base[: -len(ENDPOINTS[fmt])].rstrip("/")
    if not urlparse(base).path:
        base += VERSION_PATHS[fmt]
    return base


def request(fmt: str, baseurl: str, apikey: str, model: str, system: str, text: str,
            max_tokens: int = 16) -> str:
    url, body, headers, extract = BUILDERS[fmt](_base(fmt, baseurl), apikey, model, system, text, max_tokens)
    headers = {"Content-Type": "application/json", "User-Agent": f"KeySync/{VERSION}", **headers}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    # Fresh opener per request: urllib caches the global opener's proxy snapshot on
    # first use, so a proxy enabled after startup would never be seen.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(urllib.request.getproxies()))
    with opener.open(req, timeout=TIMEOUT_S) as response:
        return extract(json.load(response)).strip()


def test_connection() -> tuple[bool, str]:
    fmt = settings.get("polish.format")
    apikey = settings.get("polish.apikey")
    model = settings.get("polish.model")
    if not apikey:
        return False, "API key is empty"
    if not model:
        return False, "no model selected"
    try:
        text = request(fmt, settings.get("polish.baseurl"), apikey, model,
                       "Reply with the single word OK.", "ping", max_tokens=256)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read())["error"]["message"]
        except Exception:
            detail = exc.read().decode("utf-8", errors="replace")[:150]
        warn(f"polish test failed: HTTP {exc.code}: {detail}")
        return False, f"HTTP {exc.code}: {detail}"
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        warn(f"polish test failed: {detail}")
        return False, detail
    if not text:
        return False, "empty response"
    info(f"polish test ok: {text[:40]}")
    return True, text


def polish(text: str) -> str:
    delay = float(settings.get("polish.simulate_delay_s"))
    time.sleep(delay)
    info(f"polish: simulated pass, {delay:.1f}s")
    return text
