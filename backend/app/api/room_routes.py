from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.http_deps import container
from app.engine.rooms.schema import KIND_GROUP, KIND_PEER_DM

router = APIRouter()


class CreateRoomBody(BaseModel):
    title: str = ""
    role_ids: list[str] = []
    avatar: str | None = None


class UpdateRoomBody(BaseModel):
    title: str | None = None
    role_ids: list[str] | None = None
    avatar: str | None = None


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
        return delivery.create_group(
            title=body.title,
            role_ids=list(body.role_ids),
            avatar=body.avatar,
        )
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
    decorated = delivery.decorate_room(
        {
            "id": conv["id"],
            "title": conv.get("title"),
            "kind": kind,
            "avatar": conv.get("avatar"),
            "created_at": conv.get("created_at"),
            "updated_at": conv.get("updated_at"),
            "participant_role_ids": participants,
        }
    )
    return {
        **decorated,
        "peer_role_id": conv.get("peer_role_id"),
        "role_id": conv.get("role_id"),
        "messages": conv.get("messages") or [],
        "active_turn": conv.get("active_turn"),
        "older_message_count": conv.get("older_message_count") or 0,
    }


@router.patch("/rooms/{rid}")
async def update_room(rid: str, body: UpdateRoomBody, request: Request):
    _, delivery = _delivery(request)
    try:
        kwargs: dict = {}
        if body.title is not None:
            kwargs["title"] = body.title
        if body.role_ids is not None:
            kwargs["role_ids"] = list(body.role_ids)
        if "avatar" in body.model_fields_set:
            kwargs["avatar"] = body.avatar
        return delivery.update_group(rid, **kwargs)
    except KeyError as e:
        raise HTTPException(404, "房间不存在") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/rooms/{rid}")
async def delete_room(rid: str, request: Request):
    c, delivery = _delivery(request)
    try:
        delivery.get_group(rid)
        c.conversations.delete(
            rid,
            conversation_fts=getattr(c, "conversation_fts", None),
            conversation_vector=getattr(c, "conversation_vector", None),
            indexer=getattr(c, "indexer", None),
            index_revision=getattr(c, "index_revision", None),
        )
    except KeyError as e:
        raise HTTPException(404, "房间不存在") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


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
