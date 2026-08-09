from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)

# 默认窗口 / 深读窗口 / 硬上限（与 Settings 默认值对齐；运行时以注入值为准）
DEFAULT_DISCLOSURE_CHARS = 3000
DEEP_DISCLOSURE_CHARS = 16000
MAX_DISCLOSURE_CHARS = 32000

_VALID_INTENTS = frozenset({"spot", "deep"})


def resolve_disclosure_limit(
    *,
    limit: object = None,
    intent: object = None,
    default_chars: int = DEFAULT_DISCLOSURE_CHARS,
    deep_chars: int = DEEP_DISCLOSURE_CHARS,
    max_chars: int = MAX_DISCLOSURE_CHARS,
) -> int:
    """按意图解析单次披露字数：显式 limit 优先，否则 spot→default、deep→deep；最后硬封顶。"""
    try:
        max_n = max(1, int(max_chars))
    except (TypeError, ValueError):
        max_n = MAX_DISCLOSURE_CHARS
    try:
        default_n = max(1, int(default_chars))
    except (TypeError, ValueError):
        default_n = DEFAULT_DISCLOSURE_CHARS
    try:
        deep_n = max(1, int(deep_chars))
    except (TypeError, ValueError):
        deep_n = DEEP_DISCLOSURE_CHARS

    chosen: int | None = None
    if limit is not None and limit != "":
        try:
            chosen = int(limit)
        except (TypeError, ValueError):
            chosen = None
    if chosen is None:
        intent_key = str(intent or "spot").strip().lower()
        if intent_key not in _VALID_INTENTS:
            intent_key = "spot"
        chosen = deep_n if intent_key == "deep" else default_n
    return max(1, min(chosen, max_n))


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
    limit: int = DEFAULT_DISCLOSURE_CHARS,
    with_outline: bool = False,
    max_chars: int = MAX_DISCLOSURE_CHARS,
) -> dict:
    """渐进式披露：返回 [offset, offset+limit) 窗口与翻页元信息。"""
    total = len(text)
    try:
        offset = int(offset)
    except (TypeError, ValueError):
        offset = 0
    limit = resolve_disclosure_limit(limit=limit, max_chars=max_chars)
    offset = max(0, min(offset, total))
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
