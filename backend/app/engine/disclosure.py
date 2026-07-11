from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def build_outline(text: str, *, max_items: int = 50) -> list[str]:
    """抽取 Markdown 标题大纲，附各标题的字符位置，便于按 offset 直接跳转。"""
    items: list[str] = []
    for m in _HEADING_RE.finditer(text):
        level = len(m.group(1))
        title = m.group(2).strip()
        items.append(f"{'#' * level} {title} @{m.start()}")
        if len(items) >= max_items:
            break
    return items


def disclose(
    text: str,
    *,
    offset: int = 0,
    limit: int = 3000,
    with_outline: bool = False,
) -> dict:
    """渐进式披露：返回 [offset, offset+limit) 窗口与翻页元信息。"""
    total = len(text)
    try:
        offset = int(offset)
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 3000
    offset = max(0, min(offset, total))
    limit = max(1, limit)
    window = text[offset : offset + limit]
    end = offset + len(window)
    result: dict = {
        "body": window,
        "total_chars": total,
        "offset": offset,
        "returned_chars": len(window),
        "has_more": end < total,
    }
    if end < total:
        result["next_offset"] = end
    if with_outline:
        outline = build_outline(text)
        if outline:
            result["outline"] = outline
    return result


def disclosure_summary(label: str, info: dict) -> str:
    total = info["total_chars"]
    offset = info["offset"]
    end = offset + info["returned_chars"]
    if info["has_more"]:
        return (
            f"{label}：已展示 {offset + 1}-{end} / 共 {total} 字，"
            f"还有 {total - end} 字未展示（offset={info['next_offset']} 继续）"
        )
    if offset > 0:
        return f"{label}：已展示 {offset + 1}-{end} / 共 {total} 字（已到末尾）"
    return f"{label}：共 {total} 字（已全部展示）"
