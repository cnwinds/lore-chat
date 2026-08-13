from __future__ import annotations

from typing import Literal

WriteMode = Literal["auto", "merge", "replace"]


def resolve_write_mode(rel_path: str, write_mode: WriteMode) -> WriteMode:
    """auto → merge；显式 merge/replace 原样返回。"""
    if write_mode != "auto":
        return write_mode
    return "merge"
