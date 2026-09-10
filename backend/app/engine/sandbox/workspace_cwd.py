"""沙箱 cwd：同角色按会话 / 定时任务分子目录，且必须落在 /workspace。"""

from __future__ import annotations

import posixpath
from pathlib import PurePosixPath

from app.engine.sandbox.naming import safe_path_segment

WORKSPACE_ROOT = "/workspace"


def default_sandbox_cwd(
    *,
    conversation_id: str | None = None,
    schedule_id: str | None = None,
) -> str:
    """未显式 cwd 时：定时任务优先，否则会话目录，否则 /workspace。"""
    sid = (schedule_id or "").strip()
    if sid:
        return f"{WORKSPACE_ROOT}/schedules/{safe_path_segment(sid)}"
    cid = (conversation_id or "").strip()
    if cid:
        return f"{WORKSPACE_ROOT}/conversations/{safe_path_segment(cid)}"
    return WORKSPACE_ROOT


def normalize_workspace_cwd(cwd: str) -> str | dict:
    """规范化并校验 cwd 在 /workspace 下；失败返回 tool error dict。"""
    raw = (cwd or "").strip() or WORKSPACE_ROOT
    if not raw.startswith("/"):
        raw = f"{WORKSPACE_ROOT}/{raw.lstrip('/')}"
    norm = posixpath.normpath(str(PurePosixPath(raw)))
    if norm != WORKSPACE_ROOT and not norm.startswith(f"{WORKSPACE_ROOT}/"):
        return {
            "summary": "cwd 必须在 /workspace 下",
            "sources": [],
            "error": "cwd not under /workspace",
        }
    return norm


def resolve_sandbox_cwd(
    args: dict,
    *,
    conversation_id: str | None = None,
    schedule_id: str | None = None,
) -> str | dict:
    """显式 cwd 优先（仍须在 /workspace）；否则按会话 / 定时任务默认。"""
    explicit = args.get("cwd")
    if explicit is not None and str(explicit).strip():
        return normalize_workspace_cwd(str(explicit))
    return default_sandbox_cwd(
        conversation_id=conversation_id,
        schedule_id=schedule_id,
    )


__all__ = [
    "WORKSPACE_ROOT",
    "default_sandbox_cwd",
    "normalize_workspace_cwd",
    "resolve_sandbox_cwd",
]
