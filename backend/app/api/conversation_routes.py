from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.http_deps import (
    AppendMessagesBody,
    CreateConversationBody,
    ResolveBody,
    SummarizeBody,
    container,
)
from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.pending_resolver import PendingResolveInput

router = APIRouter()


@router.get("/questions")
async def questions(request: Request):
    return {"questions": container(request).pending.list_open()}


@router.post("/questions/{qid}/resolve")
async def resolve(qid: str, body: ResolveBody, request: Request):
    c = container(request)
    try:
        result = await c.pending_resolver.resolve_and_apply(
            PendingResolveInput(
                qid=qid,
                choice=body.choice,
                choices=body.choices,
                conversation_id=body.conversation_id,
            )
        )
    except KeyError as e:
        raise HTTPException(404, "问题不存在") from e
    except ValueError as e:
        msg = str(e)
        if msg == "对话不存在":
            raise HTTPException(404, msg) from e
        raise HTTPException(400, msg) from e
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"沙箱执行失败: {e}") from e
    return result.__dict__


@router.get("/conversations")
async def list_conversations(request: Request, role_id: str | None = None):
    return {
        "conversations": container(request).conversations.list_all(role_id=role_id)
    }


@router.get("/conversations/search")
async def search_conversations(
    request: Request,
    q: str = "",
    k: int = 20,
    role_id: str | None = None,
):
    """用户侧会话全文搜索（FTS）；可选按角色过滤。"""
    q = (q or "").strip()
    if not q:
        return {"hits": [], "tier": "none"}
    c = container(request)
    limit = max(1, min(int(k or 20), 50))
    # 略放大再按角色过滤
    fetch_k = limit if not role_id else min(50, limit * 3)
    outcome = c.conversation_fts.query_with_tier(q, k=fetch_k)
    hits = []
    for h in outcome.hits:
        try:
            rid = c.conversations.get_role_id(h.conversation_id)
        except KeyError:
            continue
        if role_id and rid != role_id:
            continue
        text = (h.text or "").strip().replace("\n", " ")
        if len(text) > 160:
            text = text[:157] + "…"
        hits.append(
            {
                "conversation_id": h.conversation_id,
                "message_id": h.message_id,
                "role_id": rid,
                "message_role": h.role,
                "title": h.conversation_title or "对话",
                "snippet": text,
                "ts": h.ts,
            }
        )
        if len(hits) >= limit:
            break
    return {"hits": hits, "tier": outcome.tier}


@router.post("/conversations")
async def create_conversation(
    request: Request, body: CreateConversationBody = CreateConversationBody()
):
    c = container(request)
    role_id = body.role_id
    title = body.title
    if role_id:
        try:
            c.roles.get(role_id)
        except KeyError as e:
            raise HTTPException(404, "角色不存在") from e
    else:
        role_id = c.roles.get_default()["id"]
    cid = c.conversations.create(title=title, role_id=role_id)
    return {"id": cid, "role_id": role_id}


@router.get("/conversations/{cid}/events")
async def list_conversation_events(
    cid: str,
    request: Request,
    after_event_id: str | None = None,
    limit: int = 50,
):
    c = container(request)
    try:
        c.conversations.get(cid)
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e
    events = c.conversations.system_events.list(
        cid, after_event_id=after_event_id, limit=limit
    )
    return {"events": events}


@router.get("/conversations/{cid}")
async def get_conversation(cid: str, request: Request):
    try:
        return container(request).conversations.get(cid)
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e


@router.post("/conversations/{cid}/messages")
async def append_conversation_messages(
    cid: str, body: AppendMessagesBody, request: Request
):
    try:
        return container(request).conversations.append_messages(cid, body.messages)
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e


@router.post("/conversations/{cid}/summarize")
async def summarize_conversation(cid: str, body: SummarizeBody, request: Request):
    c = container(request)
    rel_path, path_err = KnowledgeWriter.resolve_location(body.model_dump())
    if path_err:
        raise HTTPException(400, path_err.get("summary") or path_err.get("error"))
    try:
        conv = c.conversations.get(cid)
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e
    from app.engine.conversations import ConversationStore

    transcript = ConversationStore.full_transcript(conv)
    system_rules = c.system_layer.compose() if c.system_layer else ""
    try:
        result = c.organizer.summarize_conversation(
            transcript,
            conv=conv,
            forced_rel_path=rel_path,
            system_rules=system_rules,
            conversation_id=cid,
        )
    except Exception as e:
        raise HTTPException(502, f"归档失败: {e}") from e
    if result.status == "saved" and result.rel_path:
        c.conversations.summaries.mark_summarized(cid, result.rel_path)
    return result.__dict__


@router.delete("/conversations/{cid}")
async def delete_conversation(cid: str, request: Request):
    c = container(request)
    try:
        c.conversations.delete(
            cid,
            conversation_fts=c.conversation_fts,
            conversation_vector=c.conversation_vector,
            indexer=c.indexer,
            index_revision=c.index_revision,
        )
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e
    return {"ok": True}
