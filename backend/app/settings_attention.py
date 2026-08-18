"""主界面「需要处理」红点：模型必填链、记忆待确认、未填价目。"""

from __future__ import annotations

from typing import Any

from app.models.candidate import ModelChain, resolve_chain_candidates
from app.settings_store import is_llm_api_key_configured


def chain_needs_setup(settings: Any, chain: ModelChain) -> bool:
    """链上至少一条具备 model + base_url + 有效 api_key 才算已配置。"""
    for c in resolve_chain_candidates(settings, chain):
        if not (c.model or "").strip():
            continue
        if not (c.base_url or "").strip():
            continue
        if not is_llm_api_key_configured(c.api_key):
            continue
        return False
    return True


def price_row_needs_setup(row: dict[str, Any]) -> bool:
    """见过的模型若缺必填单价字段则需配置。Cache 可选。"""
    kinds = row.get("kinds") or []
    if isinstance(kinds, str):
        kinds = [k for k in kinds.split(",") if k]
    has_embed = "embed" in kinds
    has_chat = any(k != "embed" for k in kinds)
    if not has_embed and not has_chat:
        mid = str(row.get("model") or "").lower()
        has_embed = "embed" in mid
        has_chat = not has_embed
    if has_chat and (
        row.get("prompt_per_1m") is None or row.get("completion_per_1m") is None
    ):
        return True
    if has_embed and row.get("embed_per_1m") is None:
        return True
    return False


def count_incomplete_prices(prices: list[dict[str, Any]]) -> int:
    return sum(1 for row in prices if price_row_needs_setup(row))


def build_settings_attention(
    *,
    settings: Any,
    memory_pending_count: int = 0,
    incomplete_price_count: int = 0,
) -> dict[str, Any]:
    chat = chain_needs_setup(settings, "chat")
    utility = chain_needs_setup(settings, "utility")
    embed = chain_needs_setup(settings, "embed")
    model_any = chat or utility or embed
    memory_any = memory_pending_count > 0
    usage_any = incomplete_price_count > 0
    return {
        "any": model_any or memory_any or usage_any,
        "model": {
            "any": model_any,
            "chat": chat,
            "utility": utility,
            "embed": embed,
        },
        "memory": {
            "any": memory_any,
            "pending_count": int(memory_pending_count),
        },
        "usage": {
            "any": usage_any,
            "incomplete_price_count": int(incomplete_price_count),
        },
    }
