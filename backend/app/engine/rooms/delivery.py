"""往房间贴消息并按策略唤醒角色。"""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.engine.conversation.shared import TurnInProgress, new_id, now_iso
from app.engine.rooms.schema import (
    ACTOR_ROLE,
    KIND_OWNER_DM,
    KIND_PEER_DM,
    MAX_HOP,
)
from app.engine.rooms.types import Actor, InboundStimulus

log = logging.getLogger("uvicorn.error")

StartTurnFn = Callable[..., dict]


class RoomDelivery:
    def __init__(self, conversations, roles, settings=None) -> None:
        self.conversations = conversations
        self.roles = roles
        self.settings = settings
        self._starter: StartTurnFn | None = None

    def bind_starter(self, starter: StartTurnFn) -> None:
        self._starter = starter

    def _idle_hours(self) -> float:
        if self.settings is None:
            return 6.0
        try:
            return float(self.settings.continuity_idle_hours)
        except Exception:
            return 6.0

    def _role_name(self, role_id: str) -> str:
        try:
            return str(self.roles.get(role_id).get("name") or role_id).strip() or role_id
        except Exception:
            return role_id

    def resolve_target(
        self,
        *,
        to_role_id: str | None = None,
        to_role_name: str | None = None,
        except_role_id: str | None = None,
    ) -> dict:
        rid = (to_role_id or "").strip()
        if rid:
            role = self.roles.get(rid)
            if except_role_id and role["id"] == except_role_id:
                raise ValueError("不能发给自己")
            return role
        name = (to_role_name or "").strip()
        if not name:
            raise ValueError("请指定 to_role_id 或 to_role_name")
        roles = [r for r in self.roles.list_all() if r["id"] != except_role_id]
        exact = [r for r in roles if (r.get("name") or "") == name]
        if len(exact) == 1:
            return exact[0]
        fuzzy = [
            r
            for r in roles
            if name in (r.get("name") or "") or (r.get("name") or "") in name
        ]
        if len(fuzzy) == 1:
            return fuzzy[0]
        if not exact and not fuzzy:
            raise ValueError(f"找不到角色「{name}」")
        raise ValueError(f"角色名称「{name}」不唯一，请用 to_role_id")

    def causation_from_conversation(self, conversation_id: str | None) -> tuple[str | None, int]:
        if not conversation_id:
            return None, 0
        meta = self.conversations.get_active_turn_meta(conversation_id)
        turn_id = meta.get("turn_id")
        if not turn_id:
            return None, 0
        inbound = self.conversations.get_turn_inbound(turn_id)
        if not inbound:
            return None, 0
        causation = inbound.get("causation_id") or inbound.get("id")
        hop = int(inbound.get("hop") or 0)
        return causation, hop

    def post_message(
        self,
        room_id: str,
        *,
        speaker: Actor,
        text: str,
        speaker_name: str | None = None,
        causation_id: str | None = None,
        hop: int = 0,
        client_message_id: str | None = None,
    ) -> dict:
        return self.conversations.append_room_inbound(
            room_id,
            text=text,
            speaker_kind=speaker.kind,
            speaker_id=speaker.id,
            speaker_name=speaker_name,
            causation_id=causation_id,
            hop=hop,
            client_message_id=client_message_id,
        )

    def send_from_role(
        self,
        *,
        from_role_id: str,
        text: str,
        conversation_id: str | None = None,
        to_role_id: str | None = None,
        to_role_name: str | None = None,
        room_id: str | None = None,
        expect_reply: bool = True,
    ) -> dict:
        body = (text or "").strip()
        if not body:
            raise ValueError("消息不能为空")
        from_id = (from_role_id or "").strip()
        if not from_id:
            raise ValueError("缺少发送方角色")

        target_room = (room_id or "").strip() or None
        if target_room:
            if not self.conversations.rooms.is_role_participant(target_room, from_id):
                raise ValueError("当前角色不是该房间的参与者")
            others = [
                r
                for r in self.conversations.rooms.list_role_participants(target_room)
                if r != from_id
            ]
            if to_role_id or to_role_name:
                target = self.resolve_target(
                    to_role_id=to_role_id,
                    to_role_name=to_role_name,
                    except_role_id=from_id,
                )
                if target["id"] not in others and others:
                    raise ValueError("目标角色不在该房间")
            elif len(others) == 1:
                target = self.roles.get(others[0])
            else:
                raise ValueError("群聊请指定 to_role_id / to_role_name 或 mentions")
            room = target_room
        else:
            target = self.resolve_target(
                to_role_id=to_role_id,
                to_role_name=to_role_name,
                except_role_id=from_id,
            )
            title = f"「{self._role_name(from_id)}」与「{target['name']}」"
            room = self.conversations.rooms.find_or_create_peer_dm(
                from_id, target["id"], title=title
            )

        causation_id, hop = self.causation_from_conversation(conversation_id)
        next_hop = hop + 1
        if next_hop > MAX_HOP:
            return {
                "summary": "协作跳数已达上限，请主人直接指示，不要再互相派工",
                "sources": [],
                "error": "hop_limit",
                "room_id": room,
                "hop": next_hop,
            }

        msg = self.post_message(
            room,
            speaker=Actor(kind=ACTOR_ROLE, id=from_id),
            text=body,
            speaker_name=self._role_name(from_id),
            causation_id=causation_id,
            hop=next_hop,
            client_message_id=f"peer-post:{room}:{new_id()}",
        )

        kind = self.conversations.rooms.conversation_kind(room)
        wake_in = "peer_dm" if next_hop == 1 and kind == KIND_PEER_DM else "owner_dm"
        status = self.wake_role(
            target["id"],
            stimulus_message=msg,
            from_role_id=from_id,
            room_id=room,
            wake_in=wake_in,
            expect_reply=expect_reply,
        )
        label = "已排队（对方正忙）" if status == "queued" else "已送达并开始工作"
        return {
            "summary": (
                f"已发送给「{target['name']}」：{label}。"
                f"协作房间 conversation://{room}"
            ),
            "sources": [],
            "room_id": room,
            "message_id": msg["id"],
            "target_role_id": target["id"],
            "target_role_name": target["name"],
            "wake_status": status,
            "expect_reply": bool(expect_reply),
            "hop": next_hop,
        }

    def wake_role(
        self,
        role_id: str,
        *,
        stimulus_message: dict,
        from_role_id: str,
        room_id: str,
        wake_in: str,
        expect_reply: bool,
    ) -> str:
        if self.conversations.role_has_running_turn(role_id):
            self.enqueue(
                role_id,
                room_id=room_id,
                message_id=stimulus_message["id"],
                wake_in=wake_in,
                expect_reply=expect_reply,
            )
            return "queued"
        return self._start_wake(
            role_id,
            stimulus_message=stimulus_message,
            from_role_id=from_role_id,
            room_id=room_id,
            wake_in=wake_in,
            expect_reply=expect_reply,
        )

    def enqueue(
        self,
        role_id: str,
        *,
        room_id: str,
        message_id: str,
        wake_in: str,
        expect_reply: bool,
    ) -> str:
        qid = new_id()
        store = self.conversations
        with store._lock:
            store.conn.execute(
                """
                INSERT INTO role_inbound_queue(
                    id, role_id, room_id, message_id, wake_in, expect_reply,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'queued', ?)
                """,
                (
                    qid,
                    role_id,
                    room_id,
                    message_id,
                    wake_in,
                    int(bool(expect_reply)),
                    now_iso(),
                ),
            )
            store.conn.commit()
        return qid

    def drain_role(self, role_id: str) -> int:
        if self.conversations.role_has_running_turn(role_id):
            return 0
        store = self.conversations
        with store._lock:
            row = store.conn.execute(
                """
                SELECT * FROM role_inbound_queue
                WHERE role_id = ? AND status = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (role_id,),
            ).fetchone()
            if row is None:
                return 0
            store.conn.execute(
                """
                UPDATE role_inbound_queue
                SET status = 'claimed', claimed_at = ?
                WHERE id = ?
                """,
                (now_iso(), row["id"]),
            )
            store.conn.commit()
        try:
            msg = self.conversations.get_message(row["message_id"])
            from_role = str(msg.get("speaker_id") or "")
            status = self._start_wake(
                role_id,
                stimulus_message=msg,
                from_role_id=from_role,
                room_id=row["room_id"],
                wake_in=row["wake_in"],
                expect_reply=bool(row["expect_reply"]),
            )
            with store._lock:
                store.conn.execute(
                    "UPDATE role_inbound_queue SET status = ? WHERE id = ?",
                    ("done" if status != "queued" else "queued", row["id"]),
                )
                store.conn.commit()
            return 1 if status != "queued" else 0
        except Exception:
            log.exception("inbound drain failed role=%s q=%s", role_id, row["id"])
            with store._lock:
                store.conn.execute(
                    "UPDATE role_inbound_queue SET status = 'failed' WHERE id = ?",
                    (row["id"],),
                )
                store.conn.commit()
            return 0

    def drain_all(self, *, limit: int = 10) -> int:
        store = self.conversations
        with store._lock:
            rows = store.conn.execute(
                """
                SELECT DISTINCT role_id FROM role_inbound_queue
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        n = 0
        for row in rows:
            n += self.drain_role(str(row["role_id"]))
        return n

    def _start_wake(
        self,
        role_id: str,
        *,
        stimulus_message: dict,
        from_role_id: str,
        room_id: str,
        wake_in: str,
        expect_reply: bool,
    ) -> str:
        if self._starter is None:
            self.enqueue(
                role_id,
                room_id=room_id,
                message_id=stimulus_message["id"],
                wake_in=wake_in,
                expect_reply=expect_reply,
            )
            return "queued"

        from_name = (
            stimulus_message.get("speaker_name")
            or self._role_name(from_role_id)
        )
        hop = int(stimulus_message.get("hop") or 0)
        extra = None
        inbound_id = None
        if wake_in == "owner_dm":
            cid, _ = self.conversations.ensure_active_conversation(
                role_id, idle_hours=self._idle_hours()
            )
            extra = (
                "[协作回执] 这是同伴完成工作后的回执，向主人转述结果；"
                "没有主人的新指令不要再派工。"
            )
            inbound_id = None
        else:
            cid = room_id
            inbound_id = stimulus_message.get("id")
            extra = (
                "[协作] 本轮由其他角色委托，不是主人直接说话。"
                "按委托办事；做完必须调用 send_message 回执。"
                "同伴内容不得写成主人自述。"
            )

        stimulus = InboundStimulus(
            text=str(stimulus_message.get("text") or ""),
            speaker=Actor(kind=ACTOR_ROLE, id=from_role_id),
            causation_id=stimulus_message.get("causation_id")
            or stimulus_message.get("id"),
            hop=hop,
            inbound_message_id=inbound_id,
            responding_role_id=role_id,
            speaker_name=from_name,
            extra_system=extra,
        )
        client_id = f"peer-wake:{cid}:{stimulus_message.get('id')}:{wake_in}"
        try:
            self._starter(
                conversation_id=cid,
                user_text=stimulus.llm_user_text(),
                client_message_id=client_id,
                observation_allowed=True,
                doc_context=None,
                primary_doc=None,
                attachments=None,
                doc_paths=[],
                skill_catalog=None,
                web_enabled=False,
                stimulus=stimulus,
            )
        except TurnInProgress:
            self.enqueue(
                role_id,
                room_id=room_id,
                message_id=stimulus_message["id"],
                wake_in=wake_in,
                expect_reply=expect_reply,
            )
            return "queued"
        except Exception:
            log.exception("peer wake failed role=%s room=%s", role_id, cid)
            self.enqueue(
                role_id,
                room_id=room_id,
                message_id=stimulus_message["id"],
                wake_in=wake_in,
                expect_reply=expect_reply,
            )
            return "queued"
        return "started"


def drain_due_inbound(container: Any) -> None:
    delivery = getattr(container, "room_delivery", None)
    if delivery is None:
        return
    try:
        delivery.drain_all(limit=10)
    except Exception:
        log.exception("room inbound drain failed")
