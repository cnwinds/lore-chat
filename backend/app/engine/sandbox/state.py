"""沙箱运行时绑定：v2 为每角色 slot；读时迁移 v1 顶层 sandbox_id。"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.engine.roles import DEFAULT_ROLE_ID
from app.engine.sandbox.naming import (
    DEFAULT_WORKSPACE_VOLUME,
    volume_name_for_role,
)

STATE_VERSION = 2

_lock = threading.Lock()


def state_path(kb_path: Path) -> Path:
    return Path(kb_path) / ".kb" / "sandbox_runtime.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_raw(kb_path: Path) -> dict:
    path = state_path(kb_path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_raw(kb_path: Path, data: dict) -> None:
    path = state_path(kb_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _slot_dict(
    *,
    sandbox_id: str | None,
    volume_name: str,
    mirror_region: str | None,
    updated_at: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "sandbox_id": sandbox_id,
        "volume_name": volume_name,
        "updated_at": updated_at or _now(),
    }
    if mirror_region:
        out["mirror_region"] = mirror_region
    return out


def _is_v2(data: dict) -> bool:
    return data.get("version") == STATE_VERSION and isinstance(data.get("slots"), dict)


def migrate_v1_to_v2(
    data: dict,
    *,
    default_volume: str = DEFAULT_WORKSPACE_VOLUME,
    default_role_id: str = DEFAULT_ROLE_ID,
) -> dict:
    """把 v1 顶层 sandbox_id / mirror_region 迁到默认角色 slot，不丢盘。"""
    if _is_v2(data):
        slots = {}
        for key, raw in (data.get("slots") or {}).items():
            if not isinstance(key, str) or not isinstance(raw, dict):
                continue
            slots[key] = dict(raw)
        out = {
            "version": STATE_VERSION,
            "slots": slots,
        }
        if data.get("migrated_from_v1"):
            out["migrated_from_v1"] = True
        return out

    sid = data.get("sandbox_id")
    sid_s = sid.strip() if isinstance(sid, str) and sid.strip() else None
    region = data.get("mirror_region")
    region_s = (
        region.strip() if isinstance(region, str) and region.strip() else None
    )
    migrated = bool(sid_s or region_s or data)
    slots: dict[str, Any] = {}
    if sid_s or region_s:
        slots[default_role_id] = _slot_dict(
            sandbox_id=sid_s,
            volume_name=default_volume,
            mirror_region=region_s,
        )
    out: dict[str, Any] = {"version": STATE_VERSION, "slots": slots}
    if migrated and (sid_s or region_s):
        out["migrated_from_v1"] = True
    return out


def load_state(
    kb_path: Path,
    *,
    default_volume: str = DEFAULT_WORKSPACE_VOLUME,
) -> dict:
    """始终返回 v2 形态（只读规范化；不写盘）。"""
    with _lock:
        return migrate_v1_to_v2(_read_raw(kb_path), default_volume=default_volume)


def persist_v2(
    kb_path: Path,
    data: dict,
    *,
    default_volume: str = DEFAULT_WORKSPACE_VOLUME,
) -> dict:
    """规范化并落盘 v2。"""
    with _lock:
        normalized = migrate_v1_to_v2(data, default_volume=default_volume)
        _write_raw(kb_path, normalized)
        return normalized


def ensure_migrated(
    kb_path: Path,
    *,
    default_volume: str = DEFAULT_WORKSPACE_VOLUME,
) -> dict:
    """若磁盘仍是 v1，写成 v2（保留默认角色卷名与 sandbox_id）。"""
    with _lock:
        raw = _read_raw(kb_path)
        if not raw:
            empty = {"version": STATE_VERSION, "slots": {}}
            return empty
        if _is_v2(raw):
            return migrate_v1_to_v2(raw, default_volume=default_volume)
        normalized = migrate_v1_to_v2(raw, default_volume=default_volume)
        _write_raw(kb_path, normalized)
        return normalized


def get_slot(
    kb_path: Path,
    role_id: str,
    *,
    default_volume: str = DEFAULT_WORKSPACE_VOLUME,
) -> dict | None:
    rid = (role_id or "").strip() or DEFAULT_ROLE_ID
    data = load_state(kb_path, default_volume=default_volume)
    slot = (data.get("slots") or {}).get(rid)
    return dict(slot) if isinstance(slot, dict) else None


def ensure_slot(
    kb_path: Path,
    role_id: str,
    *,
    default_volume: str = DEFAULT_WORKSPACE_VOLUME,
    mirror_region: str | None = None,
) -> dict:
    """保证该角色有 slot；新角色分配独立 volume_name，默认角色沿用预创建卷。"""
    rid = (role_id or "").strip() or DEFAULT_ROLE_ID
    with _lock:
        raw = _read_raw(kb_path)
        data = migrate_v1_to_v2(raw, default_volume=default_volume)
        slots = data.setdefault("slots", {})
        existing = slots.get(rid)
        if isinstance(existing, dict) and existing.get("volume_name"):
            if mirror_region and not existing.get("mirror_region"):
                existing["mirror_region"] = mirror_region
                existing["updated_at"] = _now()
                _write_raw(kb_path, data)
            return dict(existing)
        volume = (
            existing.get("volume_name")
            if isinstance(existing, dict)
            else None
        ) or volume_name_for_role(rid, default_volume=default_volume)
        sid = existing.get("sandbox_id") if isinstance(existing, dict) else None
        region = (
            (existing.get("mirror_region") if isinstance(existing, dict) else None)
            or mirror_region
        )
        slot = _slot_dict(
            sandbox_id=sid if isinstance(sid, str) and sid.strip() else None,
            volume_name=volume,
            mirror_region=region,
        )
        slots[rid] = slot
        if raw and not _is_v2(raw) and data.get("migrated_from_v1"):
            data["migrated_from_v1"] = True
        _write_raw(kb_path, data)
        return dict(slot)


def upsert_slot(
    kb_path: Path,
    role_id: str,
    *,
    sandbox_id: str | None = None,
    volume_name: str | None = None,
    mirror_region: str | None = None,
    default_volume: str = DEFAULT_WORKSPACE_VOLUME,
    clear_sandbox_id: bool = False,
) -> dict:
    """更新一个角色 slot；不碰其他角色。"""
    rid = (role_id or "").strip() or DEFAULT_ROLE_ID
    with _lock:
        raw = _read_raw(kb_path)
        data = migrate_v1_to_v2(raw, default_volume=default_volume)
        slots = data.setdefault("slots", {})
        cur = dict(slots.get(rid) or {})
        vol = volume_name or cur.get("volume_name") or volume_name_for_role(
            rid, default_volume=default_volume
        )
        if clear_sandbox_id:
            sid = None
        elif sandbox_id is not None:
            sid = sandbox_id.strip() if isinstance(sandbox_id, str) else None
        else:
            prev = cur.get("sandbox_id")
            sid = prev if isinstance(prev, str) and prev.strip() else None
        region = mirror_region if mirror_region is not None else cur.get("mirror_region")
        slot = _slot_dict(
            sandbox_id=sid,
            volume_name=vol,
            mirror_region=region if isinstance(region, str) else None,
        )
        slots[rid] = slot
        if raw and not _is_v2(raw) and data.get("migrated_from_v1"):
            data["migrated_from_v1"] = True
        _write_raw(kb_path, data)
        return dict(slot)


def load_slot_sandbox_id(
    kb_path: Path,
    role_id: str,
    *,
    default_volume: str = DEFAULT_WORKSPACE_VOLUME,
) -> str | None:
    slot = get_slot(kb_path, role_id, default_volume=default_volume)
    if not slot:
        return None
    sid = slot.get("sandbox_id")
    return sid if isinstance(sid, str) and sid.strip() else None


def load_slot_mirror_region(
    kb_path: Path,
    role_id: str,
    *,
    default_volume: str = DEFAULT_WORKSPACE_VOLUME,
) -> str | None:
    slot = get_slot(kb_path, role_id, default_volume=default_volume)
    if not slot:
        return None
    region = slot.get("mirror_region")
    return region if isinstance(region, str) and region.strip() else None


def clear_slot_sandbox_id(
    kb_path: Path,
    role_id: str,
    *,
    default_volume: str = DEFAULT_WORKSPACE_VOLUME,
) -> None:
    """只清该角色的 sandbox_id，保留 volume 绑定。"""
    rid = (role_id or "").strip() or DEFAULT_ROLE_ID
    upsert_slot(
        kb_path,
        rid,
        clear_sandbox_id=True,
        default_volume=default_volume,
    )


# --- 兼容旧调用：默认角色 slot ---


def load_sandbox_id(kb_path: Path) -> str | None:
    return load_slot_sandbox_id(kb_path, DEFAULT_ROLE_ID)


def load_mirror_region(kb_path: Path) -> str | None:
    return load_slot_mirror_region(kb_path, DEFAULT_ROLE_ID)


def save_state(
    kb_path: Path,
    *,
    sandbox_id: str | None = None,
    mirror_region: str | None = None,
) -> None:
    upsert_slot(
        kb_path,
        DEFAULT_ROLE_ID,
        sandbox_id=sandbox_id,
        mirror_region=mirror_region,
        volume_name=None,
    )


def save_sandbox_id(kb_path: Path, sandbox_id: str) -> None:
    save_state(kb_path, sandbox_id=sandbox_id)


def clear_sandbox_id(kb_path: Path) -> None:
    """兼容：只清默认角色 sandbox_id，不删整文件、不丢其他角色绑定。"""
    clear_slot_sandbox_id(kb_path, DEFAULT_ROLE_ID)


__all__ = [
    "STATE_VERSION",
    "clear_sandbox_id",
    "clear_slot_sandbox_id",
    "ensure_migrated",
    "ensure_slot",
    "get_slot",
    "load_mirror_region",
    "load_sandbox_id",
    "load_slot_mirror_region",
    "load_slot_sandbox_id",
    "load_state",
    "migrate_v1_to_v2",
    "persist_v2",
    "save_sandbox_id",
    "save_state",
    "state_path",
    "upsert_slot",
]
