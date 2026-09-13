"""往房间贴消息并按策略唤醒角色。"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

from app.engine.conversation.shared import TurnInProgress, new_id, now_iso
from app.engine.rooms.schema import (
    ACTOR_ROLE,
    ACTOR_USER,
    KIND_GROUP,
    KIND_OWNER_DM,
    KIND_PEER_DM,
    MAX_HOP,
)
from app.engine.rooms.types import OWNER, Actor, InboundStimulus
from app.engine.roles import is_hidden_role, list_sidebar_roles

log = logging.getLogger("uvicorn.error")

StartTurnFn = Callable[..., dict]


class RoomDelivery:
    def __init__(self, conversations, roles, settings=None) -> None:
        self.conversations = conversations
        self.roles = roles
        self.settings = settings
        self._starter: StartTurnFn | None = None
        self._last_wake: dict | None = None

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

    def _require_sidebar_role(self, role: dict) -> dict:
        if is_hidden_role(role):
            raise ValueError("找不到该角色")
        return role

    def resolve_target(
        self,
        *,
        to_role_id: str | None = None,
        to_role_name: str | None = None,
        except_role_id: str | None = None,
    ) -> dict:
        rid = (to_role_id or "").strip()
        if rid:
            try:
                role = self.roles.get(rid)
            except KeyError as e:
                raise ValueError("找不到该角色") from e
            self._require_sidebar_role(role)
            if except_role_id and role["id"] == except_role_id:
                raise ValueError("不能发给自己")
            return role
        name = (to_role_name or "").strip()
        if not name:
            raise ValueError("请指定 to_role_id 或 to_role_name")
        roles = [r for r in list_sidebar_roles(self.roles) if r["id"] != except_role_id]
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

    def parse_mentions(self, mentions: Any, text: str | None = None) -> list[str]:
        raw: list[Any] = []
        if mentions:
            raw.extend(mentions if isinstance(mentions, (list, tuple)) else [mentions])
        if text:
            raw.extend(re.findall(r"@([^\s@]+)", text))
        out: list[str] = []
        seen: set[str] = set()
        for item in raw:
            token = str(item or "").strip()
            if token.startswith("@"):
                token = token[1:].strip()
            if not token or token in seen:
                continue
            seen.add(token)
            out.append(token)
        return out

    def resolve_mention_roles(
        self,
        mentions: Any,
        *,
        except_role_id: str | None = None,
        text: str | None = None,
    ) -> list[dict]:
        roles: list[dict] = []
        seen: set[str] = set()
        for token in self.parse_mentions(mentions, text):
            try:
                role = self.resolve_target(
                    to_role_id=token, except_role_id=except_role_id
                )
            except (ValueError, KeyError):
                role = self.resolve_target(
                    to_role_name=token, except_role_id=except_role_id
                )
            if role["id"] in seen:
                continue
            seen.add(role["id"])
            roles.append(role)
        return roles

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
        mentions: Any = None,
        expect_reply: bool = True,
    ) -> dict:
        body = (text or "").strip()
        if not body:
            raise ValueError("消息不能为空")
        from_id = (from_role_id or "").strip()
        if not from_id:
            raise ValueError("缺少发送方角色")

        target_room = (room_id or "").strip() or None
        mentioned = self.resolve_mention_roles(
            mentions, except_role_id=from_id, text=body
        )
        if to_role_id or to_role_name:
            named = self.resolve_target(
                to_role_id=to_role_id,
                to_role_name=to_role_name,
                except_role_id=from_id,
            )
            if all(r["id"] != named["id"] for r in mentioned):
                mentioned.insert(0, named)

        if target_room:
            if not self.conversations.rooms.is_role_participant(target_room, from_id):
                raise ValueError("当前角色不是该房间的参与者")
            others = [
                r
                for r in self.conversations.rooms.list_role_participants(target_room)
                if r != from_id
            ]
            kind = self.conversations.rooms.conversation_kind(target_room)
            if mentioned:
                for target in mentioned:
                    if target["id"] not in others and others:
                        raise ValueError(f"目标角色「{target['name']}」不在该房间")
            elif kind == KIND_PEER_DM and len(others) == 1:
                mentioned = [self._require_sidebar_role(self.roles.get(others[0]))]
            elif kind == KIND_GROUP:
                mentioned = []
            else:
                raise ValueError("群聊请指定 to_role_id / to_role_name 或 mentions")
            room = target_room
        else:
            if not mentioned:
                raise ValueError("请指定 to_role_id、to_role_name 或 mentions")
            if len(mentioned) > 1:
                raise ValueError("发给多人请先 create_room 或传入已有 room_id")
            target = mentioned[0]
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
        wake_in = self._wake_in_for(room_kind=kind, conversation_id=conversation_id)
        return self._wake_and_result(
            mentioned,
            stimulus_message=msg,
            from_role_id=from_id,
            room_id=room,
            wake_in=wake_in,
            expect_reply=expect_reply,
            hop=next_hop,
        )

    def send_from_owner(
        self,
        *,
        room_id: str,
        text: str,
        mentions: Any = None,
        client_message_id: str | None = None,
    ) -> dict:
        body = (text or "").strip()
        if not body:
            raise ValueError("消息不能为空")
        room = (room_id or "").strip()
        if not room:
            raise ValueError("缺少房间")
        kind = self.conversations.rooms.conversation_kind(room)
        if kind == KIND_OWNER_DM:
            raise ValueError("主人日常对话请走 /api/chat")

        members = self.conversations.rooms.list_role_participants(room)
        mentioned = self.resolve_mention_roles(mentions, text=body)
        for target in mentioned:
            if target["id"] not in members:
                raise ValueError(f"目标角色「{target['name']}」不在该房间")
        if not mentioned and kind == KIND_PEER_DM:
            last = self.conversations.rooms.last_responding_role_id(room)
            pick = last if last in members else (members[0] if members else None)
            if pick:
                mentioned = [self._require_sidebar_role(self.roles.get(pick))]

        msg = self.post_message(
            room,
            speaker=OWNER,
            text=body,
            speaker_name="主人",
            hop=0,
            client_message_id=client_message_id
            or f"owner-post:{room}:{new_id()}",
        )
        return self._wake_and_result(
            mentioned,
            stimulus_message=msg,
            from_role_id="",
            room_id=room,
            wake_in="room",
            expect_reply=True,
            hop=0,
            posted_only_summary="已发到房间。群聊未点名则无人自动应。",
        )

    def _wake_in_for(self, *, room_kind: str, conversation_id: str | None) -> str:
        """群里始终在本房间应；peer 从主人 tip 派工在 peer 干活，从 peer 回执回发起方 tip。"""
        if room_kind == KIND_GROUP:
            return "room"
        if room_kind != KIND_PEER_DM:
            return "owner_dm"
        source = KIND_OWNER_DM
        if conversation_id:
            try:
                source = self.conversations.rooms.conversation_kind(conversation_id)
            except Exception:
                source = KIND_OWNER_DM
        if source == KIND_PEER_DM:
            return "owner_dm"
        return "peer_dm"

    def create_group(self, *, title: str, role_ids: list[str]) -> dict:
        ids: list[str] = []
        names: list[str] = []
        for raw in role_ids:
            rid = (raw or "").strip()
            if not rid:
                continue
            try:
                role = self.roles.get(rid)
            except KeyError as e:
                raise ValueError("找不到该角色") from e
            self._require_sidebar_role(role)
            ids.append(role["id"])
            names.append(str(role.get("name") or role["id"]))
        room = self.conversations.rooms.create_group(title=title, role_ids=ids)
        return {
            "id": room,
            "title": (title or "").strip() or "群聊",
            "kind": KIND_GROUP,
            "participant_role_ids": self.conversations.rooms.list_role_participants(
                room
            ),
            "participant_names": names,
        }

    def decorate_room(self, row: dict) -> dict:
        participants = list(row.get("participant_role_ids") or [])
        names: list[str] = []
        for rid in participants:
            names.append(self._role_name(rid))
        out = dict(row)
        out["participant_names"] = names
        return out

    def list_groups(self) -> list[dict]:
        return [
            self.decorate_room(row)
            for row in self.conversations.rooms.list_groups()
        ]

    def list_rooms_for_role(self, role_id: str) -> list[dict]:
        return [
            self.decorate_room(row)
            for row in self.conversations.rooms.list_rooms_for_role(role_id)
        ]

    def collab_status(self, room_id: str, *, pending=None) -> dict:
        conv = self.conversations.get(room_id, tail=8)
        kind = conv.get("kind") or KIND_OWNER_DM
        participants = self.conversations.rooms.list_role_participants(room_id)
        queued = self.conversations.rooms.queued_count(room_id)
        active = conv.get("active_turn")
        questions = []
        if pending is not None:
            questions = [
                q
                for q in pending.list_open()
                if (q.get("payload") or {}).get("conversation_id") == room_id
            ]
        if questions:
            state = "awaiting_user"
        elif active and active.get("status") == "running":
            state = "working"
        elif queued:
            state = "queued"
        elif conv.get("messages"):
            state = "done"
        else:
            state = "idle"
        last = (conv.get("messages") or [None])[-1]
        preview = ""
        if last:
            preview = str(last.get("text") or last.get("speaker_name") or "")[:160]
        return {
            "id": room_id,
            "kind": kind,
            "title": conv.get("title"),
            "state": state,
            "preview": preview,
            "queued_count": queued,
            "pending_questions": questions,
            "active_turn": active,
            "participant_role_ids": participants,
            "participant_names": [self._role_name(r) for r in participants],
            "peer_role_id": participants[0]
            if kind == KIND_PEER_DM and len(participants) == 1
            else (
                next((r for r in participants[1:]), participants[0])
                if kind == KIND_PEER_DM and participants
                else None
            ),
            "updated_at": conv.get("updated_at"),
            "last_message_at": last.get("ts") if last else None,
        }

    def _wake_and_result(
        self,
        targets: list[dict],
        *,
        stimulus_message: dict,
        from_role_id: str,
        room_id: str,
        wake_in: str,
        expect_reply: bool,
        hop: int,
        posted_only_summary: str | None = None,
    ) -> dict:
        started: list[dict] = []
        queued: list[dict] = []
        turn_id = None
        for target in targets:
            status = self.wake_role(
                target["id"],
                stimulus_message=stimulus_message,
                from_role_id=from_role_id,
                room_id=room_id,
                wake_in=wake_in,
                expect_reply=expect_reply,
            )
            if status == "started":
                started.append(target)
                last = getattr(self, "_last_wake", None) or {}
                if turn_id is None:
                    turn = last.get("turn") or {}
                    turn_id = turn.get("turn_id")
            else:
                queued.append(target)
        first = targets[0] if targets else None
        if not targets:
            status = "posted"
            summary = posted_only_summary or (
                f"已发到房间，未点名任何人。协作房间 conversation://{room_id}"
            )
        elif started and not queued:
            status = "started"
            names = "、".join(f"「{t['name']}」" for t in started)
            summary = f"已发送给{names}：已送达并开始工作。协作房间 conversation://{room_id}"
        elif queued and not started:
            status = "queued"
            names = "、".join(f"「{t['name']}」" for t in queued)
            summary = f"已发送给{names}：已排队（对方正忙）。协作房间 conversation://{room_id}"
        else:
            status = "mixed"
            summary = (
                f"已发送：{len(started)} 人开始工作，{len(queued)} 人排队。"
                f"协作房间 conversation://{room_id}"
            )
        return {
            "summary": summary,
            "sources": [],
            "room_id": room_id,
            "message_id": stimulus_message.get("id"),
            "target_role_id": first["id"] if first else None,
            "target_role_name": first["name"] if first else None,
            "targets": [
                {"id": t["id"], "name": t["name"]} for t in targets
            ],
            "wake_status": status,
            "expect_reply": bool(expect_reply),
            "hop": hop,
            "turn_id": turn_id,
            "wake_conversation_id": room_id,
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
        if wake_in in ("room", "peer_dm") and self.conversations.room_has_running_turn(
            room_id
        ):
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

    def drain_role(self, role_id: str, conversation_id: str | None = None) -> int:
        n = self._drain_queued_for_role(role_id)
        if conversation_id:
            n += self._drain_queued_in_room(conversation_id)
        return n

    def _drain_queued_for_role(self, role_id: str) -> int:
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

    def _drain_queued_in_room(self, room_id: str) -> int:
        if self.conversations.room_has_running_turn(room_id):
            return 0
        store = self.conversations
        with store._lock:
            rows = store.conn.execute(
                """
                SELECT DISTINCT role_id FROM role_inbound_queue
                WHERE room_id = ? AND status = 'queued'
                ORDER BY created_at ASC
                """,
                (room_id,),
            ).fetchall()
        n = 0
        for row in rows:
            n += self._drain_queued_for_role(str(row["role_id"]))
            if self.conversations.room_has_running_turn(room_id):
                break
        return n

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
        speaker_kind = str(stimulus_message.get("speaker_kind") or ACTOR_ROLE)
        if wake_in == "owner_dm":
            cid, _ = self.conversations.ensure_active_conversation(
                role_id, idle_hours=self._idle_hours()
            )
            extra = (
                "[协作回执] 这是同伴完成工作后的回执，向主人转述结果；"
                "没有主人的新指令不要再派工。"
            )
            inbound_id = None
            speaker = Actor(kind=ACTOR_ROLE, id=from_role_id)
        else:
            cid = room_id
            inbound_id = stimulus_message.get("id")
            if speaker_kind == ACTOR_USER:
                speaker = OWNER
                extra = (
                    "[协作] 主人在共享房间里说话，不是单独私聊。"
                    "按指示办事；需要回执时 send_message 到本房间并点名同伴。"
                    "同伴内容不得写成主人自述。"
                )
            else:
                speaker = Actor(kind=ACTOR_ROLE, id=from_role_id)
                extra = (
                    "[协作] 本轮由其他角色委托，不是主人直接说话。"
                    "按委托办事；做完必须调用 send_message 回执。"
                    "同伴内容不得写成主人自述。"
                )

        stimulus = InboundStimulus(
            text=str(stimulus_message.get("text") or ""),
            speaker=speaker,
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
            turn = self._starter(
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
            self._last_wake = {
                "status": "started",
                "turn": turn if isinstance(turn, dict) else {},
                "conversation_id": cid,
            }
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
