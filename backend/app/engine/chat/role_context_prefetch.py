"""新段首轮：只注入本角色上一会话段的指针（标题、时间、条数），原文由模型按需用工具取回。"""

from __future__ import annotations

from app.engine.secrets import mask_secrets
from app.logging_config import get_logger
from app.time import DISPLAY_TZ_LABEL, parse_search_instant

_log = get_logger("chat.role_prefetch")


def should_prefetch_role_context(history: list[dict] | None) -> bool:
    """本段尚无用户轮次时开启（begin_turn 前快照不含本轮用户消息）。"""
    if not history:
        return True
    return not any((m.get("role") == "user") for m in history)


def build_prior_segment_pointer(conversations, *, conversation_id: str) -> str | None:
    """当前段在主人 web 一对一时间线上且有上一段时返回指针，否则不注入。"""
    if conversations is None:
        return None
    try:
        prior = conversations.prior_segment(conversation_id)
    except KeyError:
        return None
    except Exception:
        _log.warning("prior segment lookup failed cid=%s", conversation_id, exc_info=True)
        return None
    if not prior:
        return None
    cid = prior["id"]
    title, _ = mask_secrets((prior.get("title") or "").strip() or cid)
    facts = [f"[{title}](conversation://{cid})"]
    when = parse_search_instant(prior.get("last_user_message_at") or prior.get("updated_at"))
    if when is not None:
        facts.append(f"最后活动 {when.strftime('%Y-%m-%d %H:%M')}（{DISPLAY_TZ_LABEL}）")
    try:
        _, dialogue = conversations.load_dialogue_tail(cid, tail=0)
    except Exception:
        _log.warning("prior segment count failed cid=%s", cid, exc_info=True)
        dialogue = 0
    if dialogue:
        facts.append(f"对话 {dialogue} 条")
    return (
        "【上一会话段】\n"
        "本段是新会话段，之前各段原文不在 history 中。\n"
        f"- {' · '.join(facts)}"
    )
