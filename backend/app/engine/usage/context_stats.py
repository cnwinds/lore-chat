"""会话上下文统计：容量、分段占比、缓存命中率、工具调用、成本。

口径：
- used_tokens = 最近一次 LLM 调用的 prompt_tokens（圆环）；
- limit_tokens = 当前首选对话模型在 models.dev 目录中的 limit.context；
- 分项按「下一轮会真正注入」的文本估算（与 build_agent_messages / llm_history
  / select_tools 同一套装配），不再用会话全文或时间线摘要冒充。
- 汉字约 1 token/字，其它字符约 0.3 token/字；有 used_tokens 且估算偏低时，
  差额记入「工具」（当轮工具回灌未完整落盘）。
"""

from __future__ import annotations

import json
from typing import Any

from app.engine.agent.prompts import (
    MODE_DEFAULT,
    build_role_collab_block,
    build_role_identity_block,
    build_system_prompt,
    wrap_user_memory,
)
from app.engine.agent.skill_activation import build_skill_catalog_system_messages
from app.engine.agent.tool_catalog import select_tools
from app.engine.conversation.transcript import ConversationTranscript
from app.engine.disclosure import DisclosureWindows
from app.engine.roles import list_sidebar_roles
from app.models.media import attachment_is_video
from app.models.vision import is_vision_image_path

# 识图/视频没有逐帧精确公式时的保守占位（高清图常见量级）。
_VISION_TOKENS_PER_IMAGE = 765
_VISION_TOKENS_PER_VIDEO = 1000

# 按实际上下文装配顺序：系统 → 记忆 → Skill → 历史 → 工具定义/回灌 → 附件。
_SEGMENTS = (
    ("system", "系统提示词"),
    ("memory", "记忆"),
    ("skill", "Skill"),
    ("history", "历史消息"),
    ("tools", "工具与检索结果"),
    ("attachments", "附件与文档"),
)


def estimate_tokens(text: str) -> int:
    """中英混排启发式：汉字 ≈ 1 token，拉丁/符号 ≈ 0.3 token。"""
    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        code = ord(ch)
        if _is_cjk(code):
            cjk += 1
        else:
            other += 1
    return int(cjk * 1.0 + other * 0.3)


def _is_cjk(code: int) -> bool:
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2CEAF
        or 0x3000 <= code <= 0x303F
        or 0xFF00 <= code <= 0xFFEF
    )


def build_context_stats(
    *,
    conversation: dict[str, Any],
    roles,
    system_layer,
    usage_store,
    models_dev,
    chat_models: list[dict[str, Any]],
    skill_catalog: list[dict[str, str]] | None = None,
    settings=None,
    tools=None,
    role_system_prompt: str = "",
) -> dict[str, Any]:
    messages = conversation.get("messages") or []
    last_user = _last_message(messages, "user")
    web_enabled = bool((last_user or {}).get("web_enabled"))

    search_configured, imagegen_configured, sandbox_enabled, windows = (
        _capability_flags(settings, tools)
    )
    role_list = _safe_sidebar_roles(roles)
    role_messaging = len(role_list) >= 2

    memory_body = ""
    if system_layer is not None and hasattr(system_layer, "memory_context"):
        memory_body = system_layer.memory_context() or ""
    memory_block = wrap_user_memory(memory_body)

    system_text = build_system_prompt(
        MODE_DEFAULT,
        system_layer.compose_rules() if system_layer else "",
        web_enabled,
        user_memory="",
        role_system_prompt=role_system_prompt
        or _role_identity_text(roles, conversation),
        search_configured=search_configured,
    )
    if role_messaging:
        busy: set[str] = set()
        convs = getattr(tools, "conversations", None) if tools is not None else None
        if convs is not None:
            try:
                busy = set(convs.list_busy_role_ids())
            except Exception:
                busy = set()
        system_text += "\n\n" + build_role_collab_block(
            role_list,
            current_role_id=conversation.get("role_id"),
            busy_ids=busy,
        )

    skill_text = ""
    for msg in build_skill_catalog_system_messages(skill_catalog or []):
        skill_text += msg.get("content") or ""

    history_msgs = ConversationTranscript.llm_history(conversation)
    history_text = "".join(str(m.get("content") or "") for m in history_msgs)

    tool_schema = ""
    if tools is not None or settings is not None:
        selected = select_tools(
            MODE_DEFAULT,
            web_enabled,
            search_configured=search_configured,
            imagegen_configured=imagegen_configured,
            sandbox_enabled=sandbox_enabled,
            disclosure_windows=windows,
            role_messaging=role_messaging,
        )
        tool_schema = json.dumps(selected, ensure_ascii=False)
    tool_results = _last_turn_tool_text(messages)
    tools_text = tool_schema + tool_results

    attach_tokens, attach_text = _last_user_attachment_estimate(last_user)

    estimates = {
        "system": estimate_tokens(system_text),
        "memory": estimate_tokens(memory_block),
        "skill": estimate_tokens(skill_text),
        "history": estimate_tokens(history_text),
        "tools": estimate_tokens(tools_text),
        "attachments": attach_tokens + estimate_tokens(attach_text),
    }

    usage = usage_store.conversation_usage_totals(conversation.get("id") or "")
    used_tokens = usage.get("last_prompt_tokens")
    segments = _reconcile_segments(estimates, used_tokens)

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

    out_segments: list[dict[str, Any]] = []
    for key, label in _SEGMENTS:
        item: dict[str, Any] = {
            "key": key,
            "label": label,
            "tokens": segments[key],
        }
        if key == "memory":
            item["preview"] = memory_body.strip()
        out_segments.append(item)

    return {
        "model": model,
        "context": {
            "used_tokens": used_tokens,
            "limit_tokens": limit_tokens,
        },
        "segments": out_segments,
        "cache_hit_rate": cache_hit_rate,
        "tool_calls": _count_tool_calls(messages),
        "cost_total": usage.get("cost_total"),
        "turns_with_usage": usage.get("turns_with_usage", 0),
    }


def _capability_flags(settings, tools) -> tuple[bool, bool, bool, DisclosureWindows]:
    windows = DisclosureWindows()
    if settings is not None:
        windows = DisclosureWindows(
            spot=getattr(settings, "read_disclosure_chars", windows.spot),
            deep=getattr(settings, "read_disclosure_deep_chars", windows.deep),
            max_chars=getattr(settings, "read_disclosure_max_chars", windows.max_chars),
        )
    search_configured = False
    imagegen_configured = False
    sandbox_enabled = bool(getattr(settings, "sandbox_enabled", False))
    if tools is not None:
        web = getattr(tools, "web_search", None)
        search_configured = web is not None and getattr(web, "provider", None) is not None
        image_tools = getattr(tools, "image_tools", None)
        image_gen = getattr(image_tools, "image_gen", None) if image_tools else None
        imagegen_configured = bool(
            image_gen is not None and getattr(image_gen, "configured", False)
        )
        sandbox_enabled = bool(
            sandbox_enabled
            and (
                getattr(tools, "sandbox_pool", None) is not None
                or getattr(tools, "sandbox_runtime", None) is not None
                or getattr(getattr(tools, "sandbox", None), "available", False)
            )
        )
        if getattr(tools, "disclosure_windows", None) is not None:
            windows = tools.disclosure_windows
    return search_configured, imagegen_configured, sandbox_enabled, windows


def _safe_sidebar_roles(roles) -> list[dict]:
    if roles is None:
        return []
    try:
        return list_sidebar_roles(roles)
    except Exception:
        return []


def _role_identity_text(roles, conversation: dict[str, Any]) -> str:
    if roles is None:
        return ""
    try:
        rid = (conversation.get("responding_role_id") or "").strip() or (
            conversation.get("role_id") or ""
        ).strip()
        if not rid:
            return ""
        role = roles.get(rid)
        name = role.get("name") or "角色"
        prompt = role.get("system_prompt") or ""
        avatar = role.get("avatar")
        persona_id = role.get("persona_id")
        if persona_id and hasattr(roles, "get_persona"):
            try:
                persona = roles.get_persona(persona_id)
                name = persona.get("name") or name
                prompt = persona.get("system_prompt") or ""
                avatar = persona.get("avatar") or avatar
            except KeyError:
                pass
        onboarding = ""
        if role.get("onboarding_status", "none") == "active":
            onboarding = (
                f"[角色引导]\n你正在协助用户完成角色「{name}」的职责与人设定义。"
            )
        return build_role_identity_block(
            name=name,
            system_prompt=prompt,
            avatar=avatar,
            onboarding_layer=onboarding,
        )
    except KeyError:
        return ""
    except Exception:
        return ""


def _last_message(messages: list[dict], role: str) -> dict | None:
    for msg in reversed(messages):
        if msg.get("role") == role:
            return msg
    return None


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


def _last_turn_tool_text(messages: list[dict]) -> str:
    last = _last_message(messages, "assistant")
    if not last:
        return ""
    parts: list[str] = []
    for block in _walk_tool_blocks(last.get("timeline")):
        content = str(block.get("content") or "").strip()
        if content:
            parts.append(content)
            continue
        summary = str(block.get("summary") or "").strip()
        query = str(block.get("query") or "").strip()
        chunk = "\n".join(p for p in (summary, query) if p)
        if chunk:
            parts.append(chunk)
    return "\n".join(parts)


def _count_tool_calls(messages: list[dict]) -> int:
    n = 0
    for msg in messages:
        n += len(_walk_tool_blocks(msg.get("timeline")))
    return n


def _last_user_attachment_estimate(last_user: dict | None) -> tuple[int, str]:
    if not last_user:
        return 0, ""
    paths = [p for p in (last_user.get("attachments") or []) if isinstance(p, str)]
    if not paths:
        return 0, ""
    vision = 0
    other: list[str] = []
    for path in paths:
        if is_vision_image_path(path):
            vision += _VISION_TOKENS_PER_IMAGE
        elif attachment_is_video(path):
            vision += _VISION_TOKENS_PER_VIDEO
        else:
            other.append(path)
    footnote = ""
    if other:
        footnote = "（附件：" + "、".join(other) + "）"
    return vision, footnote


def _reconcile_segments(
    estimates: dict[str, int], used_tokens: int | None
) -> dict[str, int]:
    keys = [k for k, _ in _SEGMENTS]
    out = {k: max(0, int(estimates.get(k, 0))) for k in keys}
    if not used_tokens or used_tokens <= 0:
        return out
    total = sum(out.values())
    if total <= 0:
        return {k: 0 for k in keys}
    gap = used_tokens - total
    if gap > 0:
        out["tools"] = out["tools"] + gap
        return out
    factor = used_tokens / total
    scaled = {k: int(out[k] * factor) for k in keys}
    drift = used_tokens - sum(scaled.values())
    if drift != 0:
        largest = max(keys, key=lambda k: scaled[k])
        scaled[largest] += drift
    return scaled


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
