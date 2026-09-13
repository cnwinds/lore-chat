"""角色互通：房间 / 投递 / 唤醒（ADR 2026-09-12）。"""

from app.engine.rooms.delivery import RoomDelivery
from app.engine.rooms.schema import (
    KIND_GROUP,
    KIND_OWNER_DM,
    KIND_PEER_DM,
    MAX_HOP,
    OWNER_ACTOR_ID,
    ROOM_ROLE_PLACEHOLDER,
    ensure_room_schema,
)
from app.engine.rooms.store import RoomStore
from app.engine.rooms.types import Actor, InboundStimulus, format_peer_message

__all__ = [
    "Actor",
    "InboundStimulus",
    "KIND_GROUP",
    "KIND_OWNER_DM",
    "KIND_PEER_DM",
    "MAX_HOP",
    "OWNER_ACTOR_ID",
    "ROOM_ROLE_PLACEHOLDER",
    "RoomDelivery",
    "RoomStore",
    "ensure_room_schema",
    "format_peer_message",
]
