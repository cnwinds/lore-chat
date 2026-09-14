"""通道实例落盘。旧 api_keys.json 投影为 script_api，并可双写。"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.engine.api_keys import ApiKeyStore, hash_api_key, mint_api_key, verify_api_key
from app.engine.channel_plugins.secret_mask import merge_secrets, public_secrets
from app.engine.channel_plugins.types import (
    SCRIPT_API_TYPE_ID,
    STATUS_DISABLED,
    STATUS_ENABLED,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    import uuid

    return uuid.uuid4().hex[:12]


class ChannelInstanceStore:
    def __init__(self, kb_path: str | Path, *, api_keys: ApiKeyStore | None = None):
        self._path = Path(kb_path) / ".kb" / "channel_instances.json"
        self._api_keys = api_keys or ApiKeyStore(kb_path)
        self._lock = threading.Lock()

    def _load(self) -> list[dict[str, Any]]:
        if not self._path.is_file():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        items = raw.get("instances") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict) and item.get("id")]

    def _save(self, items: list[dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"instances": items}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def project_legacy_keys(self) -> int:
        """把尚未投影的 api_keys 收成 script_api 实例；脚本实例缺 Key 时双写回去。"""
        with self._lock:
            items = self._load()
            by_id = {str(item.get("id")): item for item in items}
            added = 0
            for key in self._api_keys.list_records():
                kid = str(key.get("id") or "")
                if not kid or kid in by_id:
                    continue
                inst = self._instance_from_key(key)
                items.append(inst)
                by_id[kid] = inst
                added += 1
            key_ids = {str(k.get("id") or "") for k in self._api_keys.list_records()}
            for inst in items:
                if inst.get("type_id") != SCRIPT_API_TYPE_ID:
                    continue
                if str(inst.get("id") or "") not in key_ids:
                    self._dual_write_script(inst)
            if added:
                self._save(items)
            return added

    def _instance_from_key(self, key: dict[str, Any]) -> dict[str, Any]:
        revoked = bool(key.get("revoked"))
        return {
            "id": key.get("id"),
            "type_id": SCRIPT_API_TYPE_ID,
            "name": key.get("name") or "",
            "enabled": not revoked,
            "persona_id": key.get("persona_id"),
            "role_id": key.get("role_id"),
            "config": {"key_prefix": key.get("prefix") or ""},
            "secrets": {"key_hash": key.get("hash") or ""},
            "status": STATUS_DISABLED if revoked else STATUS_ENABLED,
            "status_detail": None,
            "created_at": key.get("created_at"),
            "last_event_at": key.get("last_used_at"),
        }

    def _dual_write_script(self, inst: dict[str, Any]) -> None:
        if inst.get("type_id") != SCRIPT_API_TYPE_ID:
            return
        secrets = inst.get("secrets") or {}
        config = inst.get("config") or {}
        self._api_keys.put_record(
            {
                "id": inst.get("id"),
                "name": inst.get("name") or "",
                "hash": secrets.get("key_hash") or "",
                "prefix": config.get("key_prefix") or "",
                "persona_id": inst.get("persona_id"),
                "role_id": inst.get("role_id"),
                "revoked": not bool(inst.get("enabled")),
                "created_at": inst.get("created_at"),
                "last_used_at": inst.get("last_event_at"),
            }
        )

    def _public(self, item: dict[str, Any]) -> dict[str, Any]:
        enabled = bool(item.get("enabled"))
        status = item.get("status") or (STATUS_ENABLED if enabled else STATUS_DISABLED)
        return {
            "id": item.get("id"),
            "type_id": item.get("type_id") or SCRIPT_API_TYPE_ID,
            "name": item.get("name") or "",
            "enabled": enabled,
            "persona_id": item.get("persona_id"),
            "role_id": item.get("role_id"),
            "config": dict(item.get("config") or {}),
            "secrets": public_secrets(item.get("secrets")),
            "status": status,
            "status_detail": item.get("status_detail"),
            "created_at": item.get("created_at"),
            "last_event_at": item.get("last_event_at"),
        }

    def get_internal(self, instance_id: str) -> dict[str, Any]:
        self.project_legacy_keys()
        for item in self._load():
            if item.get("id") == instance_id:
                return {
                    **item,
                    "config": dict(item.get("config") or {}),
                    "secrets": dict(item.get("secrets") or {}),
                }
        raise KeyError(instance_id)

    def as_key(self, item: dict[str, Any]) -> dict[str, Any]:
        if "revoked" in item and "type_id" not in item:
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
        config = item.get("config") or {}
        return {
            "id": item.get("id"),
            "name": item.get("name") or "",
            "prefix": config.get("key_prefix") or "",
            "persona_id": item.get("persona_id"),
            "role_id": item.get("role_id"),
            "revoked": not bool(item.get("enabled")),
            "created_at": item.get("created_at"),
            "last_used_at": item.get("last_event_at"),
        }

    def list_all(self, *, type_id: str | None = None) -> list[dict[str, Any]]:
        self.project_legacy_keys()
        items = [self._public(item) for item in self._load()]
        if type_id:
            items = [item for item in items if item.get("type_id") == type_id]
        return items

    def get(self, instance_id: str) -> dict[str, Any]:
        self.project_legacy_keys()
        for item in self._load():
            if item.get("id") == instance_id:
                return self._public(item)
        raise KeyError(instance_id)

    def create_script(
        self,
        *,
        name: str,
        persona_id: str,
        role_id: str,
        instance_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        name = (name or "").strip()
        if not name:
            raise ValueError("通道名称不能为空")
        raw = mint_api_key()
        kid = (instance_id or _new_id()).strip()
        stamp = _now()
        record = {
            "id": kid,
            "type_id": SCRIPT_API_TYPE_ID,
            "name": name,
            "enabled": True,
            "persona_id": persona_id,
            "role_id": role_id,
            "config": {"key_prefix": raw[:12]},
            "secrets": {
                "key_hash": hash_api_key(raw),
                # 主人侧随时复制；列表接口不回传。旧实例若无此字段则无法还原明文。
                "key_plaintext": raw,
            },
            "status": STATUS_ENABLED,
            "status_detail": None,
            "created_at": stamp,
            "last_event_at": None,
        }
        with self._lock:
            items = self._load()
            items.append(record)
            self._save(items)
            self._dual_write_script(record)
        return raw, self._public(record)

    def create(
        self,
        *,
        type_id: str,
        name: str,
        persona_id: str,
        role_id: str,
        config: dict[str, Any] | None = None,
        secrets: dict[str, Any] | None = None,
        enabled: bool = True,
        status: str | None = None,
        status_detail: str | None = None,
        instance_id: str | None = None,
    ) -> dict[str, Any]:
        name = (name or "").strip()
        if not name:
            raise ValueError("通道名称不能为空")
        kid = (instance_id or _new_id()).strip()
        stamp = _now()
        enabled_flag = bool(enabled)
        record = {
            "id": kid,
            "type_id": type_id,
            "name": name,
            "enabled": enabled_flag,
            "persona_id": persona_id,
            "role_id": role_id,
            "config": dict(config or {}),
            "secrets": dict(secrets or {}),
            "status": status or (STATUS_ENABLED if enabled_flag else STATUS_DISABLED),
            "status_detail": status_detail,
            "created_at": stamp,
            "last_event_at": None,
        }
        with self._lock:
            items = self._load()
            items.append(record)
            self._save(items)
            if type_id == SCRIPT_API_TYPE_ID:
                self._dual_write_script(record)
        return self._public(record)

    def update(
        self,
        instance_id: str,
        *,
        name: str | None = None,
        persona_id: str | None = None,
        enabled: bool | None = None,
        status: str | None = None,
        status_detail: str | None = None,
        config: dict[str, Any] | None = None,
        secrets: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            items = self._load()
            found = None
            for item in items:
                if item.get("id") == instance_id:
                    found = item
                    break
            if found is None:
                raise KeyError(instance_id)
            if name is not None:
                trimmed = name.strip()
                if not trimmed:
                    raise ValueError("通道名称不能为空")
                found["name"] = trimmed
            if persona_id is not None:
                found["persona_id"] = persona_id
            if enabled is not None:
                found["enabled"] = bool(enabled)
                if status is None:
                    found["status"] = STATUS_ENABLED if enabled else STATUS_DISABLED
                    found["status_detail"] = None
            if status is not None:
                found["status"] = status
            if status_detail is not None or status is not None:
                found["status_detail"] = status_detail
            if config is not None:
                merged = dict(found.get("config") or {})
                for key, value in config.items():
                    if value is None:
                        continue
                    merged[key] = value
                found["config"] = merged
            if secrets is not None:
                found["secrets"] = merge_secrets(found.get("secrets") or {}, secrets)
            self._save(items)
            self._dual_write_script(found)
            return self._public(found)

    def set_enabled(self, instance_id: str, enabled: bool) -> dict[str, Any]:
        return self.update(instance_id, enabled=enabled)

    def touch(self, instance_id: str) -> None:
        stamp = _now()
        with self._lock:
            items = self._load()
            for item in items:
                if item.get("id") == instance_id:
                    item["last_event_at"] = stamp
                    self._save(items)
                    self._dual_write_script(item)
                    return
        self._api_keys.touch(instance_id)

    def resolve_script_token(self, raw: str) -> dict[str, Any] | None:
        self.project_legacy_keys()
        token = (raw or "").strip()
        if not token:
            return None
        for item in self._load():
            if item.get("type_id") != SCRIPT_API_TYPE_ID:
                continue
            if not item.get("enabled"):
                continue
            stored = (item.get("secrets") or {}).get("key_hash") or ""
            if stored and verify_api_key(token, stored):
                return self.as_key(self._public(item))
        rec = self._api_keys.resolve(token)
        if rec is None:
            return None
        self.project_legacy_keys()
        return rec

    def ids_for_persona(self, persona_id: str) -> list[str]:
        self.project_legacy_keys()
        return [
            str(item.get("id"))
            for item in self._load()
            if item.get("persona_id") == persona_id
        ]
