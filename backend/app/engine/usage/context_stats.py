"""会话上下文统计：读最近一次请求快照或回落用量记录。"""

from __future__ import annotations

from typing import Any

from app.engine.agent.prompt_parts import category_order_key
from app.engine.usage.model_limit import resolve_context_limit
from app.engine.usage.request_detail import build_request_detail
from app.engine.usage.request_log import RequestLogStore


def build_context_stats(
    *,
    conversation: dict[str, Any],
    usage_store,
    models_dev,
    chat_models: list[dict[str, Any]],
    request_log_store: RequestLogStore | None = None,
) -> dict[str, Any]:
    messages = conversation.get("messages") or []
    cid = conversation.get("id") or ""
    usage = usage_store.conversation_usage_totals(cid)

    latest_call_id = None
    captured_at = None
    segments: list[dict[str, Any]] = []
    used_tokens = usage.get("last_prompt_tokens")

    model = usage.get("last_model")
    limit_tokens = resolve_context_limit(
        model=model, chat_models=chat_models, models_dev=models_dev
    )

    if request_log_store is not None:
        row = request_log_store.pick_stats_row(cid)
        if row:
            latest_call_id = int(row["id"])
            captured_at = row.get("ts")
            if row.get("model"):
                model = row["model"]
            limit_tokens = resolve_context_limit(
                model=model, chat_models=chat_models, models_dev=models_dev
            )
            detail = build_request_detail(
                request_log_store,
                row,
                limit_tokens=limit_tokens,
            )
            segments = [
                {
                    "key": c["key"],
                    "label": c["label"],
                    "tokens": c["tokens"],
                }
                for c in detail.get("categories") or []
            ]
            segments.sort(key=lambda s: category_order_key(s["key"]))
            if row.get("status") == "ok" and row.get("prompt_tokens") is not None:
                used_tokens = int(row["prompt_tokens"])
            else:
                cat_sum = sum(s["tokens"] for s in segments)
                if cat_sum > 0:
                    used_tokens = cat_sum

    cache_tokens = usage.get("cache_tokens") or 0
    prompt_total = usage.get("prompt_tokens") or 0
    cache_hit_rate = (
        round(cache_tokens / prompt_total, 4)
        if prompt_total > 0 and cache_tokens > 0
        else None
    )

    return {
        "model": model,
        "context": {
            "used_tokens": used_tokens,
            "limit_tokens": limit_tokens,
        },
        "segments": segments,
        "latest_call_id": latest_call_id,
        "captured_at": captured_at,
        "cache_hit_rate": cache_hit_rate,
        "tool_calls": _count_tool_calls(messages),
        "cost_total": usage.get("cost_total"),
        "turns_with_usage": usage.get("turns_with_usage", 0),
    }


def _count_tool_calls(messages: list[dict]) -> int:
    n = 0
    for msg in messages:
        n += len(_walk_tool_blocks(msg.get("timeline")))
    return n


def _walk_tool_blocks(blocks) -> list[dict]:
    out: list[dict] = []
    if not isinstance(blocks, list):
        return out
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "parallel":
            out.extend(_walk_tool_blocks(block.get("children")))
            continue
        if block.get("type") == "tool":
            out.append(block)
    return out
