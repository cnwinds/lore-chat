"""短时媒体授权（capability URL）：供 url_wire 多模态模型公网拉取，无需会话登录。"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

# 视频处理较慢，默认 2h；与旧 signed token 600s 相比更利于上游重试
DEFAULT_MEDIA_GRANT_TTL_SEC = 7200
_GRANT_ID_BYTES = 18  # urlsafe → 24 chars
_STORE_VERSION = 1


@dataclass(frozen=True)
class MediaGrant:
    rel_path: str
    exp: float


class MediaGrantStore:
    """KB 内 `.kb/media_grants.json` 持久化；进程内可复用实例。"""

    def __init__(self, kb_path: Path) -> None:
        self._kb_path = Path(kb_path)
        self._path = self._kb_path / ".kb" / "media_grants.json"

    def issue(
        self,
        rel_path: str,
        *,
        ttl_sec: int = DEFAULT_MEDIA_GRANT_TTL_SEC,
        now: float | None = None,
    ) -> str:
        norm = rel_path.replace("\\", "/").lstrip("/")
        if not norm or norm.startswith(".kb/") or norm.startswith(".git/"):
            raise ValueError("invalid media grant path")
        now = time.time() if now is None else now
        grant_id = secrets.token_urlsafe(_GRANT_ID_BYTES)
        data = self._load()
        items: dict[str, dict] = data.setdefault("items", {})
        self._prune(items, now=now)
        items[grant_id] = {"rel_path": norm, "exp": now + max(60, int(ttl_sec))}
        self._save(data)
        return grant_id

    def resolve(self, grant_id: str, *, now: float | None = None) -> MediaGrant | None:
        if not grant_id or not _grant_id_ok(grant_id):
            return None
        now = time.time() if now is None else now
        data = self._load()
        items: dict[str, dict] = data.get("items") or {}
        row = items.get(grant_id)
        if not isinstance(row, dict):
            return None
        try:
            exp = float(row["exp"])
            rel_path = str(row["rel_path"])
        except (KeyError, TypeError, ValueError):
            return None
        if exp < now:
            items.pop(grant_id, None)
            self._save(data)
            return None
        return MediaGrant(rel_path=rel_path, exp=exp)

    def _load(self) -> dict:
        if not self._path.is_file():
            return {"version": _STORE_VERSION, "items": {}}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": _STORE_VERSION, "items": {}}
        if not isinstance(raw, dict):
            return {"version": _STORE_VERSION, "items": {}}
        items = raw.get("items")
        if not isinstance(items, dict):
            raw["items"] = {}
        return raw

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": _STORE_VERSION, "items": data.get("items") or {}}
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _prune(items: dict[str, dict], *, now: float) -> None:
        dead = []
        for gid, row in items.items():
            if not isinstance(row, dict):
                dead.append(gid)
                continue
            try:
                if float(row["exp"]) < now:
                    dead.append(gid)
            except (KeyError, TypeError, ValueError):
                dead.append(gid)
        for gid in dead:
            items.pop(gid, None)


def _grant_id_ok(grant_id: str) -> bool:
    if len(grant_id) < 16 or len(grant_id) > 64:
        return False
    for ch in grant_id:
        if not (ch.isalnum() or ch in "-_"):
            return False
    return True


def build_media_grant_url(
    *,
    public_base_url: str,
    rel_path: str,
    kb_path: Path,
    ttl_sec: int = DEFAULT_MEDIA_GRANT_TTL_SEC,
) -> str:
    grant_id = MediaGrantStore(kb_path).issue(rel_path, ttl_sec=ttl_sec)
    base = public_base_url.rstrip("/")
    return f"{base}/api/media/grant/{grant_id}"
