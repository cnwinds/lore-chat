from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.http_deps import AskBody, ChatBody, IngestBody, container, normalize_chat_context
from app.engine.chat.session_runner import consume_agent_ask, consume_agent_ingest
from app.engine.conversation.shared import TurnInProgress

router = APIRouter()


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
    """产品主入口：SSE 流式 Agent，会话持久化与时间线。"""
    c = container(request)
    doc_items, paths, skill_roots, primary = normalize_chat_context(body, c.repo)
    if body.conversation_id:
        try:
            c.conversations.get(body.conversation_id)
        except KeyError as e:
            raise HTTPException(404, "对话不存在") from e

    if not body.conversation_id:
        return StreamingResponse(
            c.chat_runner.stream_ephemeral(
                body.text,
                doc_paths=paths,
                skill_roots=skill_roots or None,
                primary_doc=primary,
                web_enabled=body.web_enabled,
            ),
            media_type="text/event-stream",
        )

    cid = body.conversation_id
    history = c.conversations.llm_history(c.conversations.get(cid))
    client_message_id = body.client_message_id or uuid.uuid4().hex
    try:
        turn = c.conversations.begin_turn(
            cid,
            user_text=body.text,
            client_message_id=client_message_id,
            observation_allowed=body.observation_allowed,
            doc_context=doc_items or None,
            primary_doc=primary,
            attachments=body.attachments or None,
        )
    except TurnInProgress as e:
        raise HTTPException(
            409,
            detail={"code": "turn_in_progress", "retry_after_ms": e.retry_after_ms},
        )

    if turn.get("status", "running") != "running":
        return StreamingResponse(
            c.chat_runner.replay_turn(turn), media_type="text/event-stream"
        )

    return StreamingResponse(
        c.chat_runner.stream_and_persist(
            body.text,
            conversation_id=cid,
            turn=turn,
            history=history,
            doc_paths=paths,
            skill_roots=skill_roots or None,
            primary_doc=primary,
            web_enabled=body.web_enabled,
        ),
        media_type="text/event-stream",
    )
