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
                inputs=body.inputs,
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


@router.get("/conversations/{cid}/queue")
async def list_send_queue(cid: str, request: Request):
    c = container(request)
    return {
        "items": c.send_queue.list_items(cid),
        "paused": c.send_queue.is_paused(cid),
    }


@router.post("/conversations/{cid}/queue")
async def enqueue_send_queue(cid: str, request: Request):
    import asyncio

    from app.engine.chat.turn_inject import PendingInject

    c = container(request)
    body = await request.json()
    item = c.send_queue.enqueue(cid, body)
    # 服务端消费：timing=inject 且当前有运行中的回合 → 立即注入并出队
    if item["timing"] == "inject" and (
        c.chat_runner.resolve_active_turn_status(cid).get("status") == "running"
    ):
        def _consume() -> None:
            c.chat_runner.enqueue_inject(
                cid,
                PendingInject(
                    text=item["text"],
                    inject_id=item["id"],
                    client_message_id=f"inject:{item['id']}",
                    doc_context=item.get("doc_context"),
                    primary_doc=item.get("primary_doc"),
                    attachments=item.get("attachments"),
                ),
            )
            c.send_queue.remove(cid, item["id"])

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _consume)
    return {"item": c.send_queue.get(cid, item["id"])}


@router.patch("/conversations/{cid}/queue/{item_id}")
async def patch_send_queue_item(cid: str, item_id: str, request: Request):
    c = container(request)
    body = await request.json()
    item = c.send_queue.update(cid, item_id, body)
    if item is None:
        raise HTTPException(404, "排队消息不存在")
    return {"item": item}


@router.post("/conversations/{cid}/queue/{item_id}/guide")
async def guide_send_queue_item(cid: str, item_id: str, request: Request):
    """引导：移到队首并注入当前信息流。"""
    c = container(request)
    c.send_queue.move_to_front(cid, item_id)
    item = c.send_queue.update(cid, item_id, {"timing": "inject"})
    if item is None:
        raise HTTPException(404, "排队消息不存在")
    # 引导 = 移到队首并立刻注入当前回合（由队列 drain 服务执行）
    c.queue_drainer.schedule_inject_consume(cid, delay=0.1)
    return {"item": item}


@router.post("/conversations/{cid}/queue/{item_id}/move")
async def move_send_queue_item(cid: str, item_id: str, request: Request):
    c = container(request)
    body = await request.json()
    direction = body.get("direction")
    if direction not in (-1, 1):
        raise HTTPException(422, "direction 须为 -1 或 1")
    c.send_queue.move(cid, item_id, direction)
    return {"ok": True}


@router.delete("/conversations/{cid}/queue/{item_id}")
async def delete_send_queue_item(cid: str, item_id: str, request: Request):
    c = container(request)
    c.send_queue.remove(cid, item_id)
    return {"ok": True}


@router.delete("/conversations/{cid}/queue")
async def clear_send_queue(cid: str, request: Request):
    c = container(request)
    c.send_queue.clear(cid)
    return {"ok": True}


@router.post("/conversations/{cid}/queue/pause")
async def pause_send_queue(cid: str, request: Request):
    c = container(request)
    body = await request.json()
    c.send_queue.set_paused(cid, bool(body.get("paused")))
    return {"paused": bool(body.get("paused"))}


@router.get("/conversations/{cid}/context-stats")
def get_conversation_context_stats(cid: str, request: Request):
    """会话上下文统计：容量、分段占比、缓存命中率、工具调用、成本。"""
    from app.engine.usage.context_stats import build_context_stats

    c = container(request)
    try:
        conv = c.conversations.get(cid)
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e
    return build_context_stats(
        conversation=conv,
        roles=c.roles,
        system_layer=c.system_layer,
        usage_store=c.usage.store,
        models_dev=c.models_dev,
        chat_models=c.settings.chat_models or [],
        skill_catalog=c.chat_runner.resolve_skill_catalog(),
    )


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
