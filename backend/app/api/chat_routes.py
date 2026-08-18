from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.http_deps import (
    AskBody,
    ChatBody,
    InjectBody,
    IngestBody,
    StopChatBody,
    container,
    normalize_chat_context,
)
from app.demo.identity import IDENTITY_GUEST
from app.demo.quota import GUEST_MAX_INPUT_CHARS, DemoQuotaExceeded
from app.auth.routes import GUEST_COOKIE
from app.engine.chat.session_runner import consume_agent_ask, consume_agent_ingest
from app.engine.chat.sse_keepalive import with_sse_keepalive
from app.engine.chat.turn_inject import PendingInject
from app.engine.conversation.shared import TurnInProgress

router = APIRouter()

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("/ingest")
async def ingest(body: IngestBody, request: Request):
    """强制落库（测试/脚本 API）。产品聊天请用 POST /api/chat。"""
    c = container(request)
    try:
        return await consume_agent_ingest(c.agent, body.text)
    except RuntimeError as e:
        raise HTTPException(502, f"录入失败: {e}") from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"录入失败: {e}") from e


@router.post("/ask")
async def ask(body: AskBody, request: Request):
    """只读问答（测试/脚本 API）。产品聊天请用 POST /api/chat。"""
    try:
        return await consume_agent_ask(container(request).agent, body.query)
    except Exception as e:
        raise HTTPException(502, f"问答失败: {e}") from e


@router.post("/chat")
async def chat(body: ChatBody, request: Request):
    """产品主入口：开始或附着观测后台 Agent 回合（SSE）。"""
    from app.engine.enabled_skills import EnabledSkillsError

    c = container(request)
    is_guest = getattr(request.state, "identity", None) == IDENTITY_GUEST
    if is_guest and body.conversation_id:
        raise HTTPException(
            403,
            detail={"code": "demo_read_only", "detail": "演示环境的对话不会被保存"},
        )
    if is_guest and len(body.text or "") > GUEST_MAX_INPUT_CHARS:
        raise HTTPException(
            400,
            detail={
                "code": "demo_input_too_long",
                "detail": f"演示环境单条提问不超过 {GUEST_MAX_INPUT_CHARS} 字",
            },
        )
    doc_items, paths, primary = normalize_chat_context(body)
    # catalog 在 runner 内装配；此处仅预解析以便缺头时返回 400（非 SSE error）
    try:
        skill_catalog = c.chat_runner.resolve_skill_catalog()
    except EnabledSkillsError as e:
        raise HTTPException(400, str(e)) from e
    if body.conversation_id:
        try:
            c.conversations.get(body.conversation_id)
        except KeyError as e:
            raise HTTPException(404, "对话不存在") from e

    if not body.conversation_id:
        history = None
        if body.ephemeral_from:
            try:
                source = c.conversations.get(body.ephemeral_from)
            except KeyError as e:
                raise HTTPException(404, "对话不存在") from e
            history = c.conversations.llm_history(source)
        if is_guest:
            quota = request.app.state.demo_quota
            guest_sid = request.cookies.get(GUEST_COOKIE) or ""
            client = request.client
            try:
                quota.acquire(guest_sid, client.host if client else None)
            except DemoQuotaExceeded as e:
                raise HTTPException(
                    429 if e.code == "demo_busy" else 403,
                    detail={"code": e.code, "detail": e.message},
                ) from e

            async def _ephemeral():
                try:
                    async for ev in c.chat_runner.stream_ephemeral(
                        body.text,
                        doc_paths=paths,
                        skill_catalog=skill_catalog,
                        primary_doc=primary,
                        web_enabled=body.web_enabled,
                        history=history,
                    ):
                        yield ev
                finally:
                    quota.release()

            stream = _ephemeral()
        else:
            stream = c.chat_runner.stream_ephemeral(
                body.text,
                doc_paths=paths,
                skill_catalog=skill_catalog,
                primary_doc=primary,
                web_enabled=body.web_enabled,
                history=history,
            )
        return StreamingResponse(
            with_sse_keepalive(stream),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    cid = body.conversation_id
    client_message_id = body.client_message_id or uuid.uuid4().hex
    try:
        turn = c.chat_runner.begin_persisted_turn(
            conversation_id=cid,
            user_text=body.text,
            client_message_id=client_message_id,
            observation_allowed=body.observation_allowed,
            doc_context=doc_items or None,
            primary_doc=primary,
            attachments=body.attachments or None,
            doc_paths=paths,
            skill_catalog=skill_catalog,
            web_enabled=body.web_enabled,
            reuse_user_message_id=body.reuse_user_message_id,
        )
    except TurnInProgress as e:
        raise HTTPException(
            409,
            detail={"code": "turn_in_progress", "retry_after_ms": e.retry_after_ms},
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    headers = {**_SSE_HEADERS, "X-Turn-Id": turn["turn_id"]}
    if turn.get("status", "running") != "running":
        return StreamingResponse(
            with_sse_keepalive(c.chat_runner.replay_turn(turn)),
            media_type="text/event-stream",
            headers=headers,
        )

    return StreamingResponse(
        with_sse_keepalive(
            c.chat_runner.observe_turn(cid, turn["turn_id"], after_seq=0)
        ),
        media_type="text/event-stream",
        headers=headers,
    )


@router.get("/conversations/{cid}/turns/active/stream")
async def observe_active_turn(
    cid: str,
    request: Request,
    after_seq: int = 0,
):
    """观测通道：附着当前内存中的活跃（或短暂保留的）回合 SSE，不启动新执行。"""
    c = container(request)
    try:
        conv = c.conversations.get(cid)
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e

    turn_id = c.chat_runner.turn_hub.resolve_turn_id(cid)
    if not turn_id:
        active = conv.get("active_turn") or {}
        if active.get("status") == "running":
            raise HTTPException(
                409,
                detail={
                    "code": "turn_orphaned",
                    "message": "回合在数据库中仍为 running，但进程内无执行任务（可能已重启）",
                },
            )
        raise HTTPException(
            404,
            detail={"code": "no_active_turn", "message": "当前没有可观测的回合"},
        )

    headers = {**_SSE_HEADERS, "X-Turn-Id": turn_id}
    return StreamingResponse(
        with_sse_keepalive(
            c.chat_runner.observe_active_turn(cid, after_seq=after_seq)
        ),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post("/chat/stop")
async def chat_stop(body: StopChatBody, request: Request):
    """显式停止当前会话的后台回合（含沙箱 interrupt）。"""
    c = container(request)
    try:
        c.conversations.get(body.conversation_id)
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e
    if not c.chat_runner.request_stop(body.conversation_id):
        raise HTTPException(
            409,
            detail={"code": "no_active_turn", "message": "当前没有可停止的回合"},
        )
    return {"status": "stopping", "conversation_id": body.conversation_id}


@router.post("/chat/inject")
async def chat_inject(body: InjectBody, request: Request):
    """Queue a user message into the active turn (A1); drained after tool results."""
    c = container(request)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    try:
        c.conversations.get(body.conversation_id)
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e

    inject_id = body.inject_id or uuid.uuid4().hex
    client_message_id = body.client_message_id or f"inject:{inject_id}"
    doc_items = [i.model_dump() for i in body.doc_context] if body.doc_context else None
    try:
        c.chat_runner.enqueue_inject(
            body.conversation_id,
            PendingInject(
                inject_id=inject_id,
                text=text,
                client_message_id=client_message_id,
                doc_context=doc_items,
                primary_doc=body.primary_doc_path,
                attachments=body.attachments or None,
            ),
        )
    except KeyError:
        raise HTTPException(
            409,
            detail={"code": "no_active_turn", "message": "当前没有可注入的回合"},
        ) from None
    return {"status": "queued", "inject_id": inject_id}
