from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.http_deps import container
from app.engine.rooms.schema import KIND_GROUP, KIND_PEER_DM

router = APIRouter()


class CreateRoomBody(BaseModel):
    title: str = ""
    role_ids: list[str] = []


class RoomMessageBody(BaseModel):
    text: str
    mentions: list[str] = []
    client_message_id: str | None = None


def _delivery(request: Request):
    c = container(request)
    delivery = getattr(c, "room_delivery", None)
    if delivery is None:
        raise HTTPException(503, "角色互通不可用")
    return c, delivery


@router.get("/rooms")
async def list_rooms(request: Request, kind: str | None = None):
    _, delivery = _delivery(request)
    want = (kind or KIND_GROUP).strip() or KIND_GROUP
    if want == KIND_GROUP:
        return {"rooms": delivery.list_groups()}
    if want == KIND_PEER_DM:
        raise HTTPException(400, "peer_dm 请走角色时间线，不单独列出")
    raise HTTPException(400, "kind 仅支持 group")


@router.post("/rooms")
async def create_room(body: CreateRoomBody, request: Request):
    _, delivery = _delivery(request)
    try:
        return delivery.create_group(title=body.title, role_ids=list(body.role_ids))
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e)) from e


@router.get("/rooms/{rid}")
async def get_room(rid: str, request: Request):
    c, delivery = _delivery(request)
    try:
        conv = c.conversations.get(rid, tail=24)
    except KeyError as e:
        raise HTTPException(404, "房间不存在") from e
    kind = conv.get("kind") or "owner_dm"
    if kind == "owner_dm":
        raise HTTPException(404, "不是协作房间")
    participants = conv.get("participant_role_ids") or []
    return {
        "id": conv["id"],
        "title": conv.get("title"),
        "kind": kind,
        "created_at": conv.get("created_at"),
        "updated_at": conv.get("updated_at"),
        "participant_role_ids": participants,
        "participant_names": [delivery._role_name(r) for r in participants],
        "peer_role_id": conv.get("peer_role_id"),
        "role_id": conv.get("role_id"),
        "messages": conv.get("messages") or [],
        "active_turn": conv.get("active_turn"),
        "older_message_count": conv.get("older_message_count") or 0,
    }


@router.get("/rooms/{rid}/status")
async def get_room_status(rid: str, request: Request):
    c, delivery = _delivery(request)
    try:
        c.conversations.get(rid, tail=1)
    except KeyError as e:
        raise HTTPException(404, "房间不存在") from e
    return delivery.collab_status(rid, pending=c.pending)


@router.post("/rooms/{rid}/messages")
async def post_room_message(rid: str, body: RoomMessageBody, request: Request):
    _, delivery = _delivery(request)
    try:
        return delivery.send_from_owner(
            room_id=rid,
            text=body.text,
            mentions=list(body.mentions or []),
            client_message_id=body.client_message_id,
        )
    except KeyError as e:
        raise HTTPException(404, "房间不存在") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
