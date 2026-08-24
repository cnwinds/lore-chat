"""分享解锁 token：密码通过后签发短时 capability，供公开 GET 携带。"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

_STORE_VERSION = 1
_UNLOCK_ID_BYTES = 18
DEFAULT_UNLOCK_TTL_SEC = 24 * 3600


@dataclass(frozen=True)
class ShareUnlock:
    share_id: str
    exp: float


class ShareUnlockStore:
    """持久化到 `{kb_path}/.kb/share_unlocks.json`。"""

    def __init__(self, kb_path: Path) -> None:
        self._kb_path = Path(kb_path)
        self._path = self._kb_path / ".kb" / "share_unlocks.json"

    def issue(
        self,
        share_id: str,
        *,
        ttl_sec: int = DEFAULT_UNLOCK_TTL_SEC,
        now: float | None = None,
    ) -> str:
        now = time.time() if now is None else now
        unlock_id = secrets.token_urlsafe(_UNLOCK_ID_BYTES)
        data = self._load()
        items: dict[str, dict] = data.setdefault("items", {})
        self._prune(items, now=now)
        items[unlock_id] = {
            "share_id": share_id,
            "exp": now + max(60, int(ttl_sec)),
        }
        self._save(data)
        return unlock_id

    def resolve(
        self, unlock_id: str, *, now: float | None = None
    ) -> ShareUnlock | None:
        if not unlock_id or not _unlock_id_ok(unlock_id):
            return None
        now = time.time() if now is None else now
        data = self._load()
        items: dict[str, dict] = data.get("items") or {}
        row = items.get(unlock_id)
        if not isinstance(row, dict):
            return None
        try:
            exp = float(row["exp"])
            share_id = str(row["share_id"])
        except (KeyError, TypeError, ValueError):
            return None
        if exp < now:
            items.pop(unlock_id, None)
            self._save(data)
            return None
        return ShareUnlock(share_id=share_id, exp=exp)

    def _load(self) -> dict:
        if not self._path.is_file():
            return {"version": _STORE_VERSION, "items": {}}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": _STORE_VERSION, "items": {}}
        if not isinstance(raw, dict):
            return {"version": _STORE_VERSION, "items": {}}
        if not isinstance(raw.get("items"), dict):
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
        for uid, row in items.items():
            if not isinstance(row, dict):
                dead.append(uid)
                continue
            try:
                if float(row["exp"]) < now:
                    dead.append(uid)
            except (KeyError, TypeError, ValueError):
                dead.append(uid)
        for uid in dead:
            items.pop(uid, None)


def _unlock_id_ok(unlock_id: str) -> bool:
    if len(unlock_id) < 16 or len(unlock_id) > 64:
        return False
    return all(ch.isalnum() or ch in "-_" for ch in unlock_id)


def unlock_ttl_for_share(exp: float | None, *, now: float) -> int:
    if exp is None:
        return DEFAULT_UNLOCK_TTL_SEC
    remaining = int(exp - now)
    return max(60, min(remaining, DEFAULT_UNLOCK_TTL_SEC))
