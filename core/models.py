"""Model files: presence check and a resumable download from the configured mirror.

The mirror's manifest gives each file's size and SHA-256. Bytes land in
<name>.part and resume with a Range request; a file takes its real name only
once its digest matches, so any model file present is complete.

UI progress is reported through emit("model", snapshot()).
"""
import hashlib
import json
import threading
import time
import urllib.request

from core.config import settings
from core.logger import error, info

BUSY = ("checking", "downloading")


def _missing() -> dict:
    targets = {settings.path(f"engine.{key}"): repo for key, repo in settings.get("models.repos").items()}
    return {path: repo for path, repo in targets.items() if not path.exists()}


def _get(url: str, **headers):
    request = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(request, timeout=float(settings.get("models.timeout_s")))


def _manifest(repo: str) -> dict:
    with _get(settings.get("models.manifest_url").format(repo=repo)) as response:
        files = json.load(response)["Data"]["Files"]
    return {f["Path"]: (f["Size"], f["Sha256"]) for f in files}


def _partial(path):
    return path.with_name(path.name + ".part")


def _offset(part, size: int) -> int:
    have = part.stat().st_size if part.exists() else 0
    if have > size:
        part.unlink()
        return 0
    return have


class ModelDownload:
    def __init__(self, emit):
        self._emit = emit
        self._lock = threading.Lock()
        self._phase = "idle"
        self._received = 0
        self._total = 0
        self._published = 0.0

    @property
    def ready(self) -> bool:
        return not _missing()

    def snapshot(self) -> dict:
        state = self._phase if self._phase != "idle" else ("ready" if self.ready else "missing")
        return {"name": settings.get("models.name"), "state": state,
                "progress": self._received / self._total if self._total else 0.0}

    def start(self) -> dict:
        with self._lock:
            if self._phase not in BUSY and not self.ready:
                self._phase = "checking"
                threading.Thread(target=self._run, daemon=True).start()
        self._publish()
        return self.snapshot()

    def _publish(self):
        self._published = time.monotonic()
        self._emit("model", self.snapshot())

    def _advance(self, n: int):
        self._received += n
        if time.monotonic() - self._published >= float(settings.get("models.progress_interval_ms")) / 1000:
            self._publish()

    def _run(self):
        info("model download: checking mirror")
        try:
            missing = _missing()
            manifests = {repo: _manifest(repo) for repo in set(missing.values())}
            plan = [(path, repo, *manifests[repo][path.name]) for path, repo in missing.items()]
            self._total = sum(size for _, _, size, _ in plan)
            self._received = sum(_offset(_partial(path), size) for path, _, size, _ in plan)
            self._phase = "downloading"
            info(f"model download: {len(plan)} files, {self._received}/{self._total} bytes present")
            self._publish()
            for item in plan:
                self._fetch(*item)
            self._phase = "idle"
            info("model download: complete")
        except Exception as exc:
            error(f"model download failed: {type(exc).__name__}: {exc}")
            self._phase = "failed"
        self._publish()

    def _fetch(self, path, repo: str, size: int, sha256: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        part = _partial(path)
        have = _offset(part, size)
        if have < size:
            url = settings.get("models.file_url").format(repo=repo, path=path.name)
            chunk = int(settings.get("models.chunk_kb")) * 1024
            with _get(url, Range=f"bytes={have}-") as response, part.open("ab") as out:
                if response.status != 206:
                    out.truncate(0)
                    self._advance(-have)
                while data := response.read(chunk):
                    out.write(data)
                    self._advance(len(data))
        if part.stat().st_size != size:
            raise ConnectionError(f"{path.name}: stream ended at {part.stat().st_size}/{size}")
        with part.open("rb") as f:
            matched = hashlib.file_digest(f, "sha256").hexdigest() == sha256
        if not matched:
            part.unlink()
            raise ValueError(f"{path.name}: checksum mismatch")
        part.replace(path)
        info(f"model download: {path.name} verified")
