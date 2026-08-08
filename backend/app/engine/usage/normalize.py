"""从 provider usage 对象规范化为可计费 token 字段。"""

from __future__ import annotations

from typing import Any


def _as_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def cached_tokens_from_usage(usage: Any) -> int | None:
    """从 OpenAI / 兼容网关 usage 中解析 cache hit tokens。"""
    if usage is None:
        return None

    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = _as_int(getattr(details, "cached_tokens", None))
        if cached is not None:
            return cached
        if isinstance(details, dict):
            cached = _as_int(details.get("cached_tokens"))
            if cached is not None:
                return cached

    cached = _as_int(getattr(usage, "prompt_cache_hit_tokens", None))
    if cached is not None:
        return cached

    input_details = getattr(usage, "input_tokens_details", None)
    if input_details is not None:
        cached = _as_int(getattr(input_details, "cached_tokens", None))
        if cached is not None:
            return cached
        if isinstance(input_details, dict):
            cached = _as_int(input_details.get("cached_tokens"))
            if cached is not None:
                return cached

    if isinstance(usage, dict):
        details = usage.get("prompt_tokens_details")
        if isinstance(details, dict):
            cached = _as_int(details.get("cached_tokens"))
            if cached is not None:
                return cached
        cached = _as_int(usage.get("prompt_cache_hit_tokens"))
        if cached is not None:
            return cached

    return None


def usage_from_resp(
    resp: Any,
) -> tuple[int | None, int | None, int | None, int | None, bool]:
    """返回 prompt, completion, total, cache, tokens_known。"""
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None, None, None, None, False
    pt = getattr(usage, "prompt_tokens", None)
    ct = getattr(usage, "completion_tokens", None)
    tt = getattr(usage, "total_tokens", None)
    if isinstance(usage, dict):
        pt = usage.get("prompt_tokens", pt)
        ct = usage.get("completion_tokens", ct)
        tt = usage.get("total_tokens", tt)
    cache = cached_tokens_from_usage(usage)
    known = pt is not None or ct is not None or tt is not None
    return pt, ct, tt, cache, known


__all__ = ["cached_tokens_from_usage", "usage_from_resp"]
