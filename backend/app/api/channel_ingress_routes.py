"""公开入站：厂商 webhook。无 Cookie。HTTP 只验签/拆 DTO，不编排 Agent。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

router = APIRouter(prefix="/channels")


def _container(request: Request):
    return request.app.state.container


@router.api_route("/{instance_id}/{type_id}", methods=["GET", "POST", "HEAD"])
async def channel_ingress(instance_id: str, type_id: str, request: Request):
    container = _container(request)
    instances = container.channel_instances
    registry = container.channel_registry
    try:
        inst = instances.get_internal(instance_id)
    except KeyError as e:
        raise HTTPException(404, "通道不存在") from e
    if inst.get("type_id") != type_id:
        raise HTTPException(404, "通道不存在")
    try:
        adapter = registry.get(type_id)
    except Exception as e:
        raise HTTPException(404, "未知通道类型") from e

    raw_bytes = await request.body()
    raw_text = raw_bytes.decode("utf-8", errors="replace") if raw_bytes else ""
    body: Any
    if raw_text.lstrip().startswith("<"):
        body = {"_raw": raw_text, "xml": raw_text}
    elif raw_text.lstrip().startswith("{") or raw_text.lstrip().startswith("["):
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            parsed = {}
        body = parsed if isinstance(parsed, dict) else {"_raw": raw_text}
        if isinstance(body, dict):
            body["_raw"] = raw_text
    else:
        body = {"_raw": raw_text}
    if isinstance(body, dict):
        body["_instance"] = inst

    raw = {
        "instance_id": instance_id,
        "body": body,
        "headers": {k: v for k, v in request.headers.items()},
        "query": {k: v for k, v in request.query_params.items()},
    }

    auth = getattr(adapter, "authenticate", None)
    if callable(auth):
        try:
            auth(inst, raw)
        except ValueError as e:
            instances.update(
                instance_id,
                status="error",
                status_detail=str(e),
            )
            raise HTTPException(401, str(e)) from e

    challenge = adapter.challenge(raw)
    if challenge is not None:
        return _challenge_response(challenge)

    if not inst.get("enabled"):
        return JSONResponse({"ok": True, "status": "ignored"})

    event = adapter.parse_inbound(raw)
    result = container.channel_turns.enqueue_now(event)
    return JSONResponse({"ok": True, **result})


def _challenge_response(challenge: Any) -> Response:
    if isinstance(challenge, dict) and "_plaintext" in challenge:
        return PlainTextResponse(str(challenge.get("_plaintext") or ""))
    if isinstance(challenge, str):
        return PlainTextResponse(challenge)
    if isinstance(challenge, (bytes, bytearray)):
        return Response(content=bytes(challenge), media_type="application/octet-stream")
    return JSONResponse(challenge if isinstance(challenge, dict) else {"ok": True})
