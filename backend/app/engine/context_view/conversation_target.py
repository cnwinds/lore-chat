"""归档等写工具用的会话 id 解析与可见性校验。"""

from __future__ import annotations

from app.engine.context_view.errors import ContextViewError, InvalidUri, NotFound, OutOfScope
from app.engine.context_view.scope import ViewScope
from app.engine.context_view.uri import ConversationUri, LegacyConversationRef, format_uri, parse
from app.engine.conversation_context import conversation_ref_id


def conversation_id_from_param(raw: str | None) -> tuple[str | None, dict | None]:
    """从 summarize 等参数的 conversation_id 提取会话 id；空表示用当前段。"""
    ref = str(raw or "").strip()
    if not ref:
        return None, None
    if ref.startswith("conversation://"):
        return conversation_ref_id(ref), None
    if not ref.startswith("lore://"):
        return ref, None
    try:
        parsed = parse(ref)
    except InvalidUri as e:
        return None, {
            "summary": str(e),
            "sources": [],
            "error": "invalid_uri",
            "uri": ref,
        }
    if isinstance(parsed, LegacyConversationRef):
        return parsed.conversation_id, None
    if isinstance(parsed, ConversationUri):
        if not parsed.conversation_id:
            return None, {
                "summary": "会话参数须指向具体会话 id",
                "sources": [],
                "error": "invalid_uri",
                "uri": ref,
            }
        return parsed.conversation_id, None
    return None, {
        "summary": "只能写知识库路径，会话参数须为会话地址或 id",
        "sources": [],
        "error": "read_only_uri",
        "uri": ref,
    }


def authorize_conversation_target(
    scope: ViewScope,
    target_cid: str,
    *,
    current_cid: str | None,
) -> dict | None:
    """非当前会话时校验可见性；当前会话或未指定 target 由调用方处理。"""
    cur = (current_cid or "").strip()
    tgt = (target_cid or "").strip()
    if not tgt or tgt == cur:
        return None
    try:
        bucket, owner = scope.conversation_bucket(tgt)
    except (KeyError, NotFound) as e:
        if isinstance(e, NotFound):
            return {
                "summary": str(e),
                "sources": [],
                "error": "not_found",
                "uri": e.uri or tgt,
            }
        return {
            "summary": "会话不存在，无法归档。",
            "sources": [],
            "error": "not_found",
            "uri": tgt,
        }
    uri = ConversationUri(bucket, owner, tgt, None, True)
    try:
        resolved = scope.resolve(format_uri(uri))
        scope.check(resolved)
    except OutOfScope as e:
        return {
            "summary": f"路径越界：{e.uri_str}",
            "sources": [],
            "error": "out_of_scope",
            "uri": e.uri_str,
        }
    except NotFound as e:
        return {
            "summary": str(e),
            "sources": [],
            "error": "not_found",
            "uri": e.uri or tgt,
        }
    except (InvalidUri, ContextViewError) as e:
        uri = getattr(e, "uri", None) or tgt
        return {
            "summary": str(e),
            "sources": [],
            "error": "invalid_uri",
            "uri": uri,
        }
    return None
