"""LLM 用量 API（设置页）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/usage", tags=["usage"])


def _usage(request: Request):
    return request.app.state.container.usage


def _channel_scope(request: Request, channel_instance_id: str | None):
    chid = (channel_instance_id or "").strip() or None
    ids = None
    if chid:
        convs = getattr(request.app.state.container, "conversations", None)
        if convs is not None and hasattr(convs, "list_ids_for_channel_instance"):
            ids = convs.list_ids_for_channel_instance(chid)
    return chid, ids


@router.get("/summary")
def usage_summary(
    request: Request,
    granularity: str = "day",
    start: str | None = None,
    end: str | None = None,
    channel_instance_id: str | None = None,
) -> dict[str, Any]:
    chid, ids = _channel_scope(request, channel_instance_id)
    try:
        return _usage(request).summary(
            granularity=granularity,
            start=start,
            end=end,
            channel_instance_id=chid,
            conversation_ids=ids,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/events")
def usage_events(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    model: str | None = None,
    channel_instance_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    chid, ids = _channel_scope(request, channel_instance_id)
    return _usage(request).events(
        start=start,
        end=end,
        model=model,
        channel_instance_id=chid,
        conversation_ids=ids,
        limit=limit,
        offset=offset,
    )


@router.get("/prices")
def usage_prices(request: Request) -> dict[str, Any]:
    return {"items": _usage(request).prices()}


@router.put("/prices")
def usage_put_price(body: dict[str, Any], request: Request) -> dict[str, Any]:
    if not body.get("model"):
        raise HTTPException(422, "model required")
    try:
        return _usage(request).upsert_price(body)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/prefs")
def usage_prefs(request: Request) -> dict[str, Any]:
    return _usage(request).prefs()


@router.put("/prefs")
def usage_put_prefs(body: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        return _usage(request).update_prefs(body)
    except Exception as e:
        raise HTTPException(422, str(e)) from e


@router.post("/clear")
def usage_clear(request: Request) -> dict[str, Any]:
    return _usage(request).clear()
