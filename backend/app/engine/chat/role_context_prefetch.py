"""新段首轮：默认检索本角色会话历史 + 知识库，注入 system 摘要。"""

from __future__ import annotations

from typing import Any

from app.logging_config import get_logger

_log = get_logger("chat.role_prefetch")

_PREFETCH_K = 5
_EXCERPT_CHARS = 280


def should_prefetch_role_context(history: list[dict] | None) -> bool:
    """本段尚无用户轮次时开启（begin_turn 前快照不含本轮用户消息）。"""
    if not history:
        return True
    return not any((m.get("role") == "user") for m in history)


def _format_hit(h: Any, *, kind: str) -> str:
    chunk = (getattr(h, "chunk", None) or "").strip().replace("\n", " ")
    if len(chunk) > _EXCERPT_CHARS:
        chunk = chunk[: _EXCERPT_CHARS - 1] + "…"
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


def build_prefetch_system_message(
    *,
    retriever,
    conversations,
    query: str,
    role_id: str,
    exclude_conversation_id: str | None,
) -> str | None:
    """执行角色会话 + KB 检索，返回可注入的 system 文本；无命中则 None。"""
    q = (query or "").strip()
    if not q or retriever is None:
        return None
    lines: list[str] = [
        "[检索摘要] 本段为新话题，上文未自动带入。以下为开场默认检索（本角色历史会话 + 知识库）。"
        "仅可依据下列命中或后续工具结果作答；禁止假装记得分隔线之前的对话原文。",
    ]
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
        lines.append("### 本角色历史会话")
        lines.extend(_format_hit(h, kind="conversation") for h in conv_hits)
    else:
        lines.append("### 本角色历史会话\n（无足够相关命中）")

    if kb_hits:
        lines.append("### 知识库")
        lines.extend(_format_hit(h, kind="kb") for h in kb_hits)
    else:
        lines.append("### 知识库\n（无足够相关命中）")

    if not conv_hits and not kb_hits:
        _log.info(
            "role prefetch empty role_id=%s exclude=%s",
            role_id,
            exclude_conversation_id,
        )
    else:
        _log.info(
            "role prefetch hits conv=%d kb=%d role_id=%s",
            len(conv_hits),
            len(kb_hits),
            role_id,
        )
    return "\n".join(lines)
