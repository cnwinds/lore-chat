"""主人签发的对外 API Key（哈希落盘，明文只在创建时返回）。"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KEY_PREFIX = "lc_live_"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    import uuid

    return uuid.uuid4().hex[:12]


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_api_key(raw: str, hashed: str) -> bool:
    try:
        return hmac.compare_digest(hash_api_key(raw), hashed)
    except (TypeError, ValueError):
        return False


def mint_api_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(24)


class ApiKeyStore:
    def __init__(self, kb_path: str | Path):
        self._path = Path(kb_path) / ".kb" / "api_keys.json"

    def _load(self) -> list[dict[str, Any]]:
        if not self._path.is_file():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        items = raw.get("keys") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            return []
        return [i for i in items if isinstance(i, dict) and i.get("id")]

    def _save(self, keys: list[dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"keys": keys}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def list_all(self) -> list[dict[str, Any]]:
        return [self._public(k) for k in self._load()]

    def get(self, key_id: str) -> dict[str, Any]:
        for item in self._load():
            if item.get("id") == key_id:
                return self._public(item)
        raise KeyError(key_id)

    def _public(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("id"),
            "name": item.get("name") or "",
            "prefix": item.get("prefix") or "",
            "persona_id": item.get("persona_id"),
            "role_id": item.get("role_id"),
            "revoked": bool(item.get("revoked")),
            "created_at": item.get("created_at"),
            "last_used_at": item.get("last_used_at"),
        }

    def create(
        self,
        *,
        name: str,
        persona_id: str,
        role_id: str,
        key_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        name = (name or "").strip()
        if not name:
            raise ValueError("密钥名称不能为空")
        kid = (key_id or _new_id()).strip()
        raw = mint_api_key()
        stamp = _now()
        record = {
            "id": kid,
            "name": name,
            "hash": hash_api_key(raw),
            "prefix": raw[:12],
            "persona_id": persona_id,
            "role_id": role_id,
            "revoked": False,
            "created_at": stamp,
            "last_used_at": None,
        }
        keys = self._load()
        keys.append(record)
        self._save(keys)
        return raw, self._public(record)

    def revoke(self, key_id: str) -> dict[str, Any]:
        keys = self._load()
        found = False
        for item in keys:
            if item.get("id") == key_id:
                item["revoked"] = True
                found = True
                break
        if not found:
            raise KeyError(key_id)
        self._save(keys)
        return self.get(key_id)

    def touch(self, key_id: str) -> None:
        keys = self._load()
        for item in keys:
            if item.get("id") == key_id:
                item["last_used_at"] = _now()
                self._save(keys)
                return

    def resolve(self, raw: str) -> dict[str, Any] | None:
        token = (raw or "").strip()
        if not token:
            return None
        digest = hash_api_key(token)
        for item in self._load():
            if item.get("revoked"):
                continue
            stored = item.get("hash") or ""
            if stored and hmac.compare_digest(digest, stored):
                return self._public(item)
        return None

    def ids_for_persona(self, persona_id: str) -> list[str]:
        return [
            str(i.get("id"))
            for i in self._load()
            if i.get("persona_id") == persona_id and not i.get("revoked")
        ]
