"""工具时间线条目的 query 字段：写入时统一截断。"""

from __future__ import annotations

TOOL_QUERY_MAX_CHARS = 1024


def clip_tool_query(text: str, *, max_chars: int = TOOL_QUERY_MAX_CHARS) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "…"
