"""新段首轮：注入上一会话段 + 默认检索本角色会话历史与知识库。"""

from __future__ import annotations

from typing import Any

from app.engine.secrets import mask_secrets
from app.logging_config import get_logger

_log = get_logger("chat.role_prefetch")

_PREFETCH_K = 5
_EXCERPT_CHARS = 280
_PRIOR_TAIL = 12
_PRIOR_MSG_CHARS = 400
_PRIOR_TOTAL_CHARS = 6000


def should_prefetch_role_context(history: list[dict] | None) -> bool:
    """本段尚无用户轮次时开启（begin_turn 前快照不含本轮用户消息）。"""
    if not history:
        return True
    return not any((m.get("role") == "user") for m in history)


def _clip(text: str, limit: int) -> str:
    chunk = (text or "").strip().replace("\n", " ")
    if len(chunk) > limit:
        return chunk[: limit - 1] + "…"
    return chunk


def _format_hit(h: Any, *, kind: str) -> str:
    chunk = _clip(getattr(h, "chunk", None) or "", _EXCERPT_CHARS)
    source = getattr(h, "source", "") or ""
    title = getattr(h, "conversation_title", None) or ""
    if kind == "conversation":
        cid = source[5:] if source.startswith("conv:") else source
        label = title or cid
        mid = getattr(h, "message_id", None)
        link = f"conversation://{cid}"
        if mid:
            link = f"{link}#{mid}"
        return f"- [{label}]({link}): {chunk}"
    return f"- [{source}]: {chunk}"


def _format_prior_segment(
    conversations, *, role_id: str, exclude_conversation_id: str | None
) -> list[str]:
    if conversations is None:
        return ["### 本角色上一会话段\n（无）"]
    try:
        prior = conversations.latest_prior_owner_dm(
            role_id, exclude_conversation_id=exclude_conversation_id
        )
    except Exception:
        _log.warning("role prefetch prior lookup failed", exc_info=True)
        return ["### 本角色上一会话段\n（读取失败）"]
    if not prior:
        return ["### 本角色上一会话段\n（无）"]
    cid = prior["id"]
    title = (prior.get("title") or cid).strip()
    try:
        raw, older = conversations.load_dialogue_tail(cid, tail=_PRIOR_TAIL)
    except Exception:
        _log.warning("role prefetch prior load failed cid=%s", cid, exc_info=True)
        return [f"### 本角色上一会话段\n- [{title}](conversation://{cid})（正文读取失败）"]
    messages = [m for m in raw if (m.get("text") or "").strip()]
    last_id = messages[-1]["id"] if messages else None
    link = f"conversation://{cid}/{last_id}" if last_id else f"conversation://{cid}"
    lines = [
        "### 本角色上一会话段",
        f"- [{title}]({link})",
        "用户未点明的指代与接续默认指向此段，不是后面相关度检索里的旧命中。",
    ]
    if older:
        lines.append(f"共更早还有 {older} 条未列出；不足时对该 conversation_id 检索或向前读取。")
    used = 0
    for m in messages:
        masked, _ = mask_secrets(m.get("text") or "")
        excerpt = _clip(masked, _PRIOR_MSG_CHARS)
        if not excerpt:
            continue
        if used + len(excerpt) > _PRIOR_TOTAL_CHARS:
            excerpt = _clip(excerpt, max(32, _PRIOR_TOTAL_CHARS - used))
            lines.append(f"  - {m.get('role')}: {excerpt}")
            lines.append("  - …（已达注入预算）")
            break
        lines.append(f"  - {m.get('role')}: {excerpt}")
        used += len(excerpt)
    if not messages:
        lines.append("  （该段没有可展示的对话原文）")
    return lines


def build_prefetch_system_message(
    *,
    retriever,
    conversations,
    query: str,
    role_id: str,
    exclude_conversation_id: str | None,
) -> str | None:
    """上一会话段（确定性）+ 角色会话 / KB 相关度检索。"""
    lines: list[str] = [
        "[检索摘要] 本段为新话题，上文未自动带入。"
        "下列「上一会话段」是本角色时间线上最近一段有内容的对话；"
        "其后是开场相关度检索（可能更旧，不能代替上一会话段）。"
        "仅可依据下列内容或后续工具结果作答；禁止假装记得分隔线之前未列出的原文。",
    ]
    lines.extend(
        _format_prior_segment(
            conversations,
            role_id=role_id,
            exclude_conversation_id=exclude_conversation_id,
        )
    )

    q = (query or "").strip()
    conv_hits: list[Any] = []
    kb_hits: list[Any] = []
    if q and retriever is not None:
        try:
            conv_page = retriever.search(
                q,
                k=_PREFETCH_K,
                scope="conversations",
                exclude_conversation_id=exclude_conversation_id,
                role_id=role_id,
            )
            conv_hits = list(conv_page.hits or [])
        except TypeError:
            # 旧签名无 role_id 时回退并后过滤
            try:
                conv_page = retriever.search(
                    q,
                    k=_PREFETCH_K * 3,
                    scope="conversations",
                    exclude_conversation_id=exclude_conversation_id,
                )
                conv_hits = []
                for h in conv_page.hits or []:
                    src = getattr(h, "source", "") or ""
                    if not src.startswith("conv:"):
                        continue
                    cid = src[5:]
                    try:
                        if conversations.get_role_id(cid) != role_id:
                            continue
                    except KeyError:
                        continue
                    conv_hits.append(h)
                    if len(conv_hits) >= _PREFETCH_K:
                        break
            except Exception:
                _log.warning("role prefetch conversations failed", exc_info=True)
                conv_hits = []
        except Exception:
            _log.warning("role prefetch conversations failed", exc_info=True)
            conv_hits = []

        try:
            kb_page = retriever.search(q, k=_PREFETCH_K, scope="knowledge")
            kb_hits = list(kb_page.hits or [])
        except Exception:
            _log.warning("role prefetch knowledge failed", exc_info=True)
            kb_hits = []

    if conv_hits:
        lines.append("### 相关历史会话（按相关度，可能早于上一会话段）")
        lines.extend(_format_hit(h, kind="conversation") for h in conv_hits)
    else:
        lines.append("### 相关历史会话\n（无足够相关命中）")

    if kb_hits:
        lines.append("### 知识库")
        lines.extend(_format_hit(h, kind="kb") for h in kb_hits)
    else:
        lines.append("### 知识库\n（无足够相关命中）")

    _log.info(
        "role prefetch hits conv=%d kb=%d role_id=%s exclude=%s",
        len(conv_hits),
        len(kb_hits),
        role_id,
        exclude_conversation_id,
    )
    return "\n".join(lines)
