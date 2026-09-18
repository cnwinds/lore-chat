"""对外脚本 API：Bearer Key，前缀 /api/v1。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.api.http_deps import container
from app.engine.chat.sse_keepalive import with_sse_keepalive
from app.engine.conversation.shared import TurnInProgress
from app.engine.open_api import OpenApiError

router = APIRouter(prefix="/v1")

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


class V1ChatBody(BaseModel):
    message: str
    conversation_id: str | None = None
    skills: list[str] = Field(default_factory=list)
    title: str | None = None
    wait: bool = True
    timeout_sec: float = 120
    stream: bool = False


def _api_key(request: Request) -> dict:
    rec = getattr(request.state, "api_key", None)
    if not rec:
        raise HTTPException(401, detail={"code": "api_key_required", "message": "api key required"})
    return rec


def _raise_open(err: OpenApiError) -> None:
    raise HTTPException(
        err.status,
        detail={"code": err.code, "message": str(err)},
    ) from err


@router.post("/chat")
async def v1_chat(body: V1ChatBody, request: Request):
    key = _api_key(request)
    svc = container(request).open_api
    try:
        if body.stream:
            cid, turn = svc.begin_chat(
                key=key,
                message=body.message,
                conversation_id=body.conversation_id,
                skills=body.skills or None,
                title=body.title,
            )
            headers = {
                **_SSE_HEADERS,
                "X-Turn-Id": turn["turn_id"],
                "X-Conversation-Id": cid,
            }
            return StreamingResponse(
                with_sse_keepalive(
                    svc.iter_chat_sse(key=key, conversation_id=cid, turn=turn)
                ),
                media_type="text/event-stream",
                headers=headers,
            )
        result = await svc.complete_chat(
            key=key,
            message=body.message,
            conversation_id=body.conversation_id,
            skills=body.skills or None,
            title=body.title,
            timeout_sec=body.timeout_sec if body.wait else 0.05,
        )
    except TurnInProgress as e:
        raise HTTPException(
            409,
            detail={"code": "turn_in_progress", "retry_after_ms": e.retry_after_ms},
        ) from e
    except OpenApiError as e:
        _raise_open(e)
    except KeyError as e:
        raise HTTPException(404, detail={"code": "not_found", "message": "不存在"}) from e
    status = result.get("status")
    code = 202 if status == "running" else 200
    return JSONResponse(result, status_code=code)


@router.get("/conversations")
async def v1_list_conversations(request: Request):
    key = _api_key(request)
    items = container(request).open_api.list_key_conversations(key["id"])
    return {"conversations": items}


@router.get("/conversations/{cid}")
async def v1_get_conversation(cid: str, request: Request, tail: int | None = None):
    key = _api_key(request)
    svc = container(request).open_api
    try:
        svc._assert_key_conversation(key, cid)
        conv = container(request).conversations.get(cid, tail=tail)
    except OpenApiError as e:
        _raise_open(e)
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e
    return conv


@router.get("/conversations/{cid}/turns/{turn_id}")
async def v1_get_turn(cid: str, turn_id: str, request: Request):
    key = _api_key(request)
    svc = container(request).open_api
    try:
        svc._assert_key_conversation(key, cid)
    except OpenApiError as e:
        _raise_open(e)
    row = container(request).conversations.get_turn(turn_id)
    if row is None or row.get("conversation_id") != cid:
        raise HTTPException(404, "回合不存在")
    return row


@router.post("/conversations/{cid}/stop")
async def v1_stop(cid: str, request: Request):
    key = _api_key(request)
    c = container(request)
    try:
        c.open_api._assert_key_conversation(key, cid)
    except OpenApiError as e:
        _raise_open(e)
    if not c.chat_runner.request_stop(cid):
        raise HTTPException(
            409,
            detail={"code": "no_active_turn", "message": "当前没有可停止的回合"},
        )
    return {"status": "stopping", "conversation_id": cid}


@router.get("/skills")
async def v1_skills(request: Request):
    _api_key(request)
    from app.engine.enabled_skills import EnabledSkillsError

    try:
        catalog = container(request).chat_runner.resolve_skill_catalog()
    except EnabledSkillsError as e:
        raise HTTPException(400, str(e)) from e
    return {"skills": catalog}
