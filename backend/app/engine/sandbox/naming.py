"""角色沙箱卷名与路径段：docker-safe slug。"""

from __future__ import annotations

import hashlib
import re

from app.engine.roles import DEFAULT_ROLE_ID

# Docker / PVC 名：字母数字开头，仅 [a-z0-9][a-z0-9_.-]
_UNSAFE = re.compile(r"[^a-z0-9]+")
_ID_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

DEFAULT_WORKSPACE_VOLUME = "lorechat-sandbox-workspace"
VOLUME_PREFIX = "lorechat-sandbox-ws"
# claim 名宜短于 63（K8s DNS label）
_SLUG_MAX = 40


def volume_slug(role_id: str, *, max_len: int = _SLUG_MAX) -> str:
    """把 role_id 收成 docker-safe 短段。"""
    raw = (role_id or "").strip().lower()
    slug = _UNSAFE.sub("-", raw).strip("-")
    if not slug:
        slug = "role"
    if slug[0].isdigit():
        slug = f"r-{slug}"
    if len(slug) > max_len:
        digest = hashlib.sha256((role_id or "").encode("utf-8")).hexdigest()[:8]
        keep = max(8, max_len - 9)
        slug = f"{slug[:keep].rstrip('-')}-{digest}"
    return slug


def volume_name_for_role(
    role_id: str,
    *,
    default_volume: str = DEFAULT_WORKSPACE_VOLUME,
    default_role_id: str = DEFAULT_ROLE_ID,
) -> str:
    """默认角色沿用 compose 预创建卷；其余角色独立 PVC 名。"""
    rid = (role_id or "").strip() or default_role_id
    if rid == default_role_id:
        return default_volume
    return f"{VOLUME_PREFIX}-{volume_slug(rid)}"


def safe_path_segment(raw: str, *, fallback: str = "id") -> str:
    """会话 / 定时任务 id 用作 /workspace 子目录名。"""
    text = (raw or "").strip()
    cleaned = _ID_UNSAFE.sub("-", text).strip(".-")
    if not cleaned:
        return fallback
    return cleaned[:80]


__all__ = [
    "DEFAULT_WORKSPACE_VOLUME",
    "VOLUME_PREFIX",
    "safe_path_segment",
    "volume_name_for_role",
    "volume_slug",
]
