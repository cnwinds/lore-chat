from __future__ import annotations

from dataclasses import dataclass
import re

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)

# 默认窗口 / 深读窗口 / 硬上限（Settings 默认值应引用此处）
DEFAULT_DISCLOSURE_CHARS = 3000
DEEP_DISCLOSURE_CHARS = 16000
MAX_DISCLOSURE_CHARS = 32000

_VALID_INTENTS = frozenset({"spot", "deep"})


def _as_positive_int(value: object, fallback: int) -> int:
    try:
        return max(1, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return max(1, fallback)


def resolve_disclosure_limit(
    *,
    limit: object = None,
    intent: object = None,
    default_chars: int = DEFAULT_DISCLOSURE_CHARS,
    deep_chars: int = DEEP_DISCLOSURE_CHARS,
    max_chars: int = MAX_DISCLOSURE_CHARS,
) -> int:
    """按意图解析单次披露字数。

    - spot（默认）：默认小窗；显式 limit 也不得超过小窗。
    - deep：默认深读窗；显式 limit 可放大，但不超过硬上限。
    """
    max_n = _as_positive_int(max_chars, MAX_DISCLOSURE_CHARS)
    default_n = min(_as_positive_int(default_chars, DEFAULT_DISCLOSURE_CHARS), max_n)
    deep_n = min(_as_positive_int(deep_chars, DEEP_DISCLOSURE_CHARS), max_n)

    intent_key = str(intent or "spot").strip().lower()
    if intent_key not in _VALID_INTENTS:
        intent_key = "spot"
    ceiling = max_n if intent_key == "deep" else default_n

    chosen: int | None = None
    if limit is not None and limit != "":
        try:
            chosen = int(limit)
        except (TypeError, ValueError):
            chosen = None
    if chosen is None:
        chosen = deep_n if intent_key == "deep" else default_n
    return max(1, min(chosen, ceiling))


@dataclass(frozen=True)
class DisclosureWindows:
    """渐进式披露窗口配置（spot / deep / 硬上限）。"""

    spot: int = DEFAULT_DISCLOSURE_CHARS
    deep: int = DEEP_DISCLOSURE_CHARS
    max_chars: int = MAX_DISCLOSURE_CHARS

    def resolve(self, *, limit: object = None, intent: object = None) -> int:
        return resolve_disclosure_limit(
            limit=limit,
            intent=intent,
            default_chars=self.spot,
            deep_chars=self.deep,
            max_chars=self.max_chars,
        )

    def resolve_args(self, args: dict) -> int:
        return self.resolve(limit=args.get("limit"), intent=args.get("intent"))


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
    """渐进式披露：返回 [offset, offset+limit) 窗口与翻页元信息。

    limit 视为已选定的窗口大小；此处只做硬上限截断（意图解析在工具层完成）。
    """
    total = len(text)
    try:
        offset = int(offset)
    except (TypeError, ValueError):
        offset = 0
    max_n = _as_positive_int(max_chars, MAX_DISCLOSURE_CHARS)
    try:
        limit_n = int(limit)
    except (TypeError, ValueError):
        limit_n = DEFAULT_DISCLOSURE_CHARS
    limit_n = max(1, min(limit_n, max_n))
    offset = max(0, min(offset, total))
    window = text[offset : offset + limit_n]
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
