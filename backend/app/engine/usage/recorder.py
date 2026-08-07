"""从 LLMClient 写入用量事件。"""

from __future__ import annotations

from typing import Any

from app.engine.usage.context import get_usage_context
from app.engine.usage.store import UsageStore, _utc_now


def compute_cost(
    *,
    kind: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    prompt_per_1k: float | None,
    completion_per_1k: float | None,
    embed_per_1k: float | None,
) -> float | None:
    if kind == "embed":
        if embed_per_1k is None:
            return None
        n = total_tokens if total_tokens is not None else prompt_tokens
        if n is None:
            return None
        return round((n / 1000.0) * float(embed_per_1k), 8)
    if prompt_per_1k is None and completion_per_1k is None:
        return None
    cost = 0.0
    have = False
    if prompt_tokens is not None and prompt_per_1k is not None:
        cost += (prompt_tokens / 1000.0) * float(prompt_per_1k)
        have = True
    if completion_tokens is not None and completion_per_1k is not None:
        cost += (completion_tokens / 1000.0) * float(completion_per_1k)
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
        tokens_known: bool = False,
        status: str = "ok",
        error: str | None = None,
        duration_ms: int | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
    ) -> str:
        ctx = get_usage_context()
        price = self.store.get_price(model) or {}
        prompt_p = price.get("prompt_per_1k")
        completion_p = price.get("completion_per_1k")
        embed_p = price.get("embed_per_1k")
        cost = None
        if tokens_known and status == "ok":
            cost = compute_cost(
                kind=kind,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                prompt_per_1k=prompt_p,
                completion_per_1k=completion_p,
                embed_per_1k=embed_p,
            )
        event: dict[str, Any] = {
            "ts": _utc_now(),
            "model": model,
            "kind": kind,
            "role": role,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "tokens_known": bool(tokens_known),
            "prompt_price_per_1k": prompt_p,
            "completion_price_per_1k": completion_p,
            "embed_price_per_1k": embed_p,
            "cost": cost,
            "status": status,
            "error": error,
            "duration_ms": duration_ms,
            "conversation_id": conversation_id or ctx.conversation_id,
            "turn_id": turn_id or ctx.turn_id,
        }
        return self.store.insert_event(event)
