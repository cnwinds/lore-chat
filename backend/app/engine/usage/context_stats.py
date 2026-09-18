"""会话上下文统计：容量、分段占比、缓存命中率、工具调用、成本。

口径：
- used_tokens = 最近一次 LLM 调用的 prompt_tokens（即当时的全部上下文）；
- limit_tokens = 当前首选对话模型在 models.dev 目录中的 limit.context；
- segments 为估算值（字符数 × 0.75），已知 used_tokens 时按比例归一，
  使分项占比与真实总量一致。
"""

from __future__ import annotations

from typing import Any

from app.engine.agent.skill_activation import build_skill_catalog_system_messages

TOKENS_PER_CHAR = 0.75

# 按实际上下文装配顺序排列：系统提示词在最前，其后为历史消息，
# 工具结果与附件随消息注入（前端容量条按此顺序分段着色）。
_SEGMENTS = (
    ("system", "系统提示词"),
    ("history", "历史消息"),
    ("tools", "工具与检索结果"),
    ("skill", "Skill"),
    ("attachments", "附件与文档"),
)


def _segment_tokens(chars: int) -> int:
    return int(chars * TOKENS_PER_CHAR)


def build_context_stats(
    *,
    conversation: dict[str, Any],
    roles,
    system_layer,
    usage_store,
    models_dev,
    chat_models: list[dict[str, Any]],
    skill_catalog: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    messages = conversation.get("messages") or []

    history_chars = 0
    tool_chars = 0
    tool_calls = 0
    for m in messages:
        history_chars += len(m.get("text") or "")
        for block in m.get("timeline") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool":
                tool_calls += 1
            tool_chars += len(str(block.get("summary") or ""))
            tool_chars += len(str(block.get("title") or ""))

    system_chars = len(system_layer.compose() or "")
    role_id = conversation.get("role_id")
    if role_id:
        try:
            role = roles.get(role_id)
            system_chars += len(role.get("system_prompt") or "")
        except KeyError:
            pass

    attachments = 0
    for m in messages:
        attachments += len(m.get("attachments") or [])
    # Skill 分段：启用技能目录注入 system message 的真实字符量
    skill_chars = 0
    for msg in build_skill_catalog_system_messages(skill_catalog or []):
        skill_chars += len(msg.get("content") or "")

    estimates = {
        "history": _segment_tokens(history_chars),
        "system": _segment_tokens(system_chars),
        "tools": _segment_tokens(tool_chars),
        "skill": _segment_tokens(skill_chars),
        "attachments": attachments * _segment_tokens(200),
    }

    usage = usage_store.conversation_usage_totals(
        conversation.get("id") or ""
    )
    used_tokens = usage.get("last_prompt_tokens")
    segments = _scale_segments(estimates, used_tokens)

    model = usage.get("last_model") or _first_chat_model(chat_models)
    limit_tokens = None
    if model:
        provider = _provider_for_model(chat_models, model)
        limit_tokens = models_dev.context_limit(model, provider)

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
        "segments": [
            {"key": key, "label": label, "tokens": segments[key]}
            for key, label in _SEGMENTS
        ],
        "cache_hit_rate": cache_hit_rate,
        "tool_calls": tool_calls,
        "cost_total": usage.get("cost_total"),
        "turns_with_usage": usage.get("turns_with_usage", 0),
    }


def _scale_segments(
    estimates: dict[str, int], used_tokens: int | None
) -> dict[str, int]:
    keys = [k for k, _ in _SEGMENTS]
    total = sum(estimates.get(k, 0) for k in keys)
    if total <= 0:
        return {k: 0 for k in keys}
    if not used_tokens or used_tokens <= 0:
        return {k: int(estimates.get(k, 0)) for k in keys}
    factor = used_tokens / total
    return {k: int(estimates.get(k, 0) * factor) for k in keys}


def _first_chat_model(chat_models: list[dict[str, Any]]) -> str | None:
    for c in chat_models or []:
        m = (c.get("model") or "").strip()
        if m:
            return m
    return None


def _provider_for_model(
    chat_models: list[dict[str, Any]], model: str
) -> str | None:
    for c in chat_models or []:
        if (c.get("model") or "").strip() == model:
            return (c.get("provider") or "").strip() or None
    return None
