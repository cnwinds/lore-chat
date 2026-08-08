from __future__ import annotations

from pathlib import PurePosixPath

MEMORY_DOC_REL = "系统/记忆.md"


def normalize_kb_rel(path: str) -> str:
    """折叠 . / .. 与多余斜杠，得到稳定相对路径。"""
    raw = (path or "").replace("\\", "/").lstrip("/")
    parts: list[str] = []
    for part in PurePosixPath(raw).parts:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def is_memory_projection_path(path: str | None) -> bool:
    if not path:
        return False
    return normalize_kb_rel(path) == MEMORY_DOC_REL

ORIGIN_RANK = {
    "inferred": 0,
    "direct": 1,
    "explicit_remember": 2,
    "manual": 3,
}

CATEGORIES = frozenset(
    {"identity", "preference", "goal", "project", "workflow", "constraint"}
)

SECTION_BY_CATEGORY: dict[str, str] = {
    "identity": "身份与稳定背景",
    "preference": "偏好与沟通方式",
    "goal": "长期目标与持续方向",
    "project": "长期目标与持续方向",
    "workflow": "工作方式与工具环境",
    "constraint": "关键约束",
}

DEFAULT_MEMORY_MAX_CHARS = 4000
