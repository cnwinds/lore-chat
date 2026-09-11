from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from pydantic import BaseModel

from app.api.http_deps import (
    AppendMessagesBody,
    CreateConversationBody,
    ResolveBody,
    SummarizeBody,
    container,
)
from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.pending_resolver import PendingResolveInput
from app.engine.workspace_search import search_workspace

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
    scope: str = "messages",
):
    """用户侧工作区搜索：会话 FTS+向量，可选角色名与知识库；可按角色过滤消息。"""
    c = container(request)
    return search_workspace(
        retriever=c.retriever,
        conversations=c.conversations,
        roles=c.roles,
        q=q,
        k=k,
        scope=scope,
        role_id=role_id,
    )


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
async def get_conversation(
    cid: str,
    request: Request,
    tail: int | None = None,
    around_id: str | None = None,
    radius: int | None = None,
):
    """取会话。``around_id`` 优先：只返回锚点附近一小窗，避免搜索跳转拉全量。"""
    tail_n: int | None = None
    if tail is not None:
        tail_n = max(1, min(int(tail), 80))
    around = (around_id or "").strip() or None
    radius_n: int | None = None
    if radius is not None:
        radius_n = max(1, min(int(radius), 40))
    try:
        return container(request).conversations.get(
            cid, tail=tail_n, around_id=around, radius=radius_n
        )
    except KeyError as e:
        detail = str(e).strip("'\"")
        if detail == "消息不存在":
            raise HTTPException(404, "消息不存在") from e
        raise HTTPException(404, "对话不存在") from e


@router.get("/conversations/{cid}/messages")
async def list_conversation_messages(
    cid: str,
    request: Request,
    before_id: str | None = None,
    limit: int = 16,
):
    """向前翻页：``before_id`` 之前的一页消息（正序）。"""
    if not before_id:
        raise HTTPException(400, "before_id 必填")
    page_limit = max(1, min(int(limit or 16), 80))
    try:
        messages, older = container(request).conversations.load_messages_before(
            cid, before_id=before_id, limit=page_limit
        )
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e
    return {"messages": messages, "older_message_count": older}


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
