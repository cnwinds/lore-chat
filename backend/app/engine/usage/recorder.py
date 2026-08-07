"""从 LLMClient 写入用量事件。"""

from __future__ import annotations

from typing import Any

from app.engine.usage.context import get_usage_context
from app.engine.usage.store import UsageStore, _utc_now

# 价目单位：每百万 tokens（与厂商价目表一致）
_TOKENS_PER_UNIT = 1_000_000.0


def compute_cost(
    *,
    kind: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    cache_tokens: int | None = None,
    prompt_per_1m: float | None,
    completion_per_1m: float | None,
    cache_input_per_1m: float | None = None,
    embed_per_1m: float | None,
) -> float | None:
    if kind == "embed":
        if embed_per_1m is None:
            return None
        n = total_tokens if total_tokens is not None else prompt_tokens
        if n is None:
            return None
        return round((n / _TOKENS_PER_UNIT) * float(embed_per_1m), 8)

    cached = int(cache_tokens or 0)
    if cached < 0:
        cached = 0
    if prompt_tokens is not None:
        cached = min(cached, int(prompt_tokens))

    if (
        prompt_per_1m is None
        and completion_per_1m is None
        and cache_input_per_1m is None
    ):
        return None

    cost = 0.0
    have = False

    if prompt_tokens is not None:
        uncached = max(0, int(prompt_tokens) - cached)
        if uncached and prompt_per_1m is not None:
            cost += (uncached / _TOKENS_PER_UNIT) * float(prompt_per_1m)
            have = True
        if cached:
            cache_price = (
                cache_input_per_1m
                if cache_input_per_1m is not None
                else prompt_per_1m
            )
            if cache_price is not None:
                cost += (cached / _TOKENS_PER_UNIT) * float(cache_price)
                have = True

    if completion_tokens is not None and completion_per_1m is not None:
        cost += (completion_tokens / _TOKENS_PER_UNIT) * float(completion_per_1m)
        have = True

    return round(cost, 8) if have else None


class UsageRecorder:
    def __init__(self, store: UsageStore):
        self.store = store

    def record(
        self,
        *,
        model: str,
        kind: str,
        role: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        cache_tokens: int | None = None,
        tokens_known: bool = False,
        status: str = "ok",
        error: str | None = None,
        duration_ms: int | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
    ) -> str:
        ctx = get_usage_context()
        price = self.store.get_price(model) or {}
        prompt_p = price.get("prompt_per_1m")
        completion_p = price.get("completion_per_1m")
        cache_p = price.get("cache_input_per_1m")
        embed_p = price.get("embed_per_1m")
        cost = None
        if tokens_known and status == "ok":
            cost = compute_cost(
                kind=kind,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cache_tokens=cache_tokens,
                prompt_per_1m=prompt_p,
                completion_per_1m=completion_p,
                cache_input_per_1m=cache_p,
                embed_per_1m=embed_p,
            )
        event: dict[str, Any] = {
            "ts": _utc_now(),
            "model": model,
            "kind": kind,
            "role": role,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cache_tokens": cache_tokens,
            "tokens_known": bool(tokens_known),
            "prompt_price_per_1m": prompt_p,
            "completion_price_per_1m": completion_p,
            "cache_input_price_per_1m": cache_p,
            "embed_price_per_1m": embed_p,
            "cost": cost,
            "status": status,
            "error": error,
            "duration_ms": duration_ms,
            "conversation_id": conversation_id or ctx.conversation_id,
            "turn_id": turn_id or ctx.turn_id,
        }
        return self.store.insert_event(event)
