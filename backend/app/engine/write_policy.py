from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

WriteMode = Literal["auto", "merge", "replace"]


def resolve_write_mode(rel_path: str, write_mode: WriteMode) -> WriteMode:
    """SKILL.md 默认 replace，避免 Organizer 合并剥掉正文内 YAML。"""
    if write_mode != "auto":
        return write_mode
    if PurePosixPath(rel_path).name.upper() == "SKILL.MD":
        return "replace"
    return "merge"
