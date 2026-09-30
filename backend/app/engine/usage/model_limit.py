"""对话模型上下文窗口上限（共用）。"""

from __future__ import annotations

from typing import Any


def first_chat_model(chat_models: list[dict[str, Any]]) -> str | None:
    for c in chat_models or []:
        m = (c.get("model") or "").strip()
        if m:
            return m
    return None


def provider_for_model(chat_models: list[dict[str, Any]], model: str) -> str | None:
    for c in chat_models or []:
        if (c.get("model") or "").strip() == model:
            return (c.get("provider") or "").strip() or None
    return None


def resolve_context_limit(
    *,
    model: str | None,
    chat_models: list[dict[str, Any]],
    models_dev,
) -> int | None:
    if not model:
        model = first_chat_model(chat_models)
    if not model:
        return None
    provider = provider_for_model(chat_models, model)
    return models_dev.context_limit(model, provider)
