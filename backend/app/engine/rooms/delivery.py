"""往房间贴消息并按策略唤醒角色。"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any, Callable

from app.engine.conversation.shared import TurnInProgress, new_id, now_iso
from app.engine.rooms.assignments import GroupAssignmentLedger
from app.engine.rooms.schema import (
    ACTOR_ROLE,
    ACTOR_SYSTEM,
    ACTOR_USER,
    KIND_GROUP,
    KIND_OWNER_DM,
    KIND_PEER_DM,
    MAX_HOP,
)
from app.engine.rooms.types import OWNER, SYSTEM, Actor, InboundStimulus
from app.engine.roles import is_hidden_role, list_sidebar_roles

log = logging.getLogger("uvicorn.error")

StartTurnFn = Callable[..., dict]

_WORKER_EXTRA = (
    "[协作] 你在本群舞台上用当前角色执行（人设与沙箱是你的）。"
    "按委托办事；做完把回执 send_message 贴回本群即可，不必再点名派工者，系统会叫醒对方。"
    "不要另开一对一房间；同伴内容不得写成主人自述。"
)
_COORDINATOR_RECEIPT_EXTRA = (
    "[协调] 同伴已回执。向群里（主人可见）汇总进度；未完成的继续追问或改派。"
    "没有主人的新指令不要另开一对一房间，也不要把回执写成主人自述。"
)
_COORDINATOR_OVERDUE_EXTRA = (
    "[协调] 你派出去的任务已超过预期、尚未收回执。"
    "用自己的声音向工人询问进度或改派；不要假扮系统，不要另开一对一房间，"
    "也不要打断工人正在跑的沙箱。"
)
_OWNER_IN_ROOM_EXTRA = (
    "[协作] 主人在共享房间里说话，不是单独私聊。"
    "按指示办事；回执 send_message 贴回本房间即可。"
    "同伴内容不得写成主人自述。"
)


class RoomDelivery:
    def __init__(self, conversations, roles, settings=None) -> None:
        self.conversations = conversations
        self.roles = roles
        self.settings = settings
        self.assignments = GroupAssignmentLedger(conversations)
        self._starter: StartTurnFn | None = None
        self._last_wake: dict | None = None
        self._post_locks_guard = threading.Lock()
        self._post_locks: dict[str, threading.Lock] = {}

    def bind_starter(self, starter: StartTurnFn) -> None:
        self._starter = starter

    def _room_post_lock(self, room_id: str) -> threading.Lock:
        with self._post_locks_guard:
            lock = self._post_locks.get(room_id)
            if lock is None:
                lock = threading.Lock()
                self._post_locks[room_id] = lock
            return lock

    def _default_due_minutes(self) -> int:
        if self.settings is None:
            return 15
        try:
            return max(1, min(24 * 60, int(self.settings.group_assignment_due_minutes)))
        except Exception:
            return 15

    @staticmethod
    def _parse_due_minutes(raw: Any) -> int | None:
        if raw is None or raw is False:
            return None
        try:
            n = int(raw)
        except (TypeError, ValueError):
            return None
        return max(1, min(24 * 60, n))

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
        due_in_minutes: int | None = None,
    ) -> dict:
        body = (text or "").strip()
        if not body:
            raise ValueError("消息不能为空")
        from_id = (from_role_id or "").strip()
        if not from_id:
            raise ValueError("缺少发送方角色")

        target_room = (room_id or "").strip() or None
        if not target_room and conversation_id:
            try:
                if (
                    self.conversations.rooms.conversation_kind(conversation_id)
                    == KIND_GROUP
                ):
                    target_room = conversation_id
            except KeyError:
                pass
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

        due_minutes = self._parse_due_minutes(due_in_minutes)
        if due_minutes is None:
            due_minutes = self._default_due_minutes()

        with self._room_post_lock(room):
            return self._post_and_wake_from_role(
                from_id=from_id,
                body=body,
                room=room,
                mentioned=mentioned,
                causation_id=causation_id,
                next_hop=next_hop,
                conversation_id=conversation_id,
                expect_reply=expect_reply,
                due_minutes=due_minutes,
            )

    def _post_and_wake_from_role(
        self,
        *,
        from_id: str,
        body: str,
        room: str,
        mentioned: list[dict],
        causation_id: str | None,
        next_hop: int,
        conversation_id: str | None,
        expect_reply: bool,
        due_minutes: int,
    ) -> dict:
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
        closed: dict | None = None
        if kind == KIND_GROUP:
            closed = self.assignments.close_oldest_open(
                room_id=room,
                assignee_role_id=from_id,
                receipt_message_id=msg.get("id"),
            )
            if expect_reply:
                for target in mentioned:
                    self.assignments.open(
                        room_id=room,
                        assigner_role_id=from_id,
                        assignee_role_id=target["id"],
                        source_message_id=msg.get("id"),
                        brief=body,
                        due_in_minutes=due_minutes,
                    )
        wake_in = self._wake_in_for(room_kind=kind, conversation_id=conversation_id)
        result = self._wake_and_result(
            mentioned,
            stimulus_message=msg,
            from_role_id=from_id,
            room_id=room,
            wake_in=wake_in,
            expect_reply=expect_reply,
            hop=next_hop,
        )
        if kind == KIND_GROUP and closed:
            assigner = str(closed.get("assigner_role_id") or "")
            already = {t["id"] for t in mentioned}
            if assigner and assigner != from_id and assigner not in already:
                status = self.wake_role(
                    assigner,
                    stimulus_message=msg,
                    from_role_id=from_id,
                    room_id=room,
                    wake_in="room_lead",
                    expect_reply=True,
                    extra_system=_COORDINATOR_RECEIPT_EXTRA,
                )
                result = dict(result)
                result["receipt_to"] = assigner
                result["receipt_wake_status"] = status
            result = dict(result)
            result["end_turn"] = True
            summary = str(result.get("summary") or "")
            if "本回合到此结束" not in summary:
                result["summary"] = (
                    f"{summary} 已回执给协调者，本回合到此结束。".strip()
                )
        return result

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

    def _role_brief(self, rid: str) -> dict:
        try:
            role = self.roles.get(rid)
            return {
                "id": rid,
                "name": str(role.get("name") or rid),
                "avatar": role.get("avatar"),
            }
        except Exception:
            return {"id": rid, "name": self._role_name(rid), "avatar": None}

    def _resolve_member_ids(self, role_ids: list[str] | None) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        for raw in role_ids or []:
            rid = (raw or "").strip()
            if not rid or rid in seen:
                continue
            try:
                role = self.roles.get(rid)
            except KeyError as e:
                raise ValueError("找不到该角色") from e
            self._require_sidebar_role(role)
            seen.add(role["id"])
            ids.append(role["id"])
        return ids

    def create_group(
        self,
        *,
        title: str,
        role_ids: list[str],
        avatar: str | None = None,
    ) -> dict:
        ids = self._resolve_member_ids(role_ids)
        room = self.conversations.rooms.create_group(
            title=title, role_ids=ids, avatar=avatar
        )
        return self.decorate_room(self.conversations.rooms.get_group(room))

    def update_group(
        self,
        cid: str,
        *,
        title: str | None = None,
        avatar: str | None | object = ...,
        role_ids: list[str] | None = None,
    ) -> dict:
        members = self._resolve_member_ids(role_ids) if role_ids is not None else None
        updated = self.conversations.rooms.update_group(
            cid, title=title, avatar=avatar, role_ids=members
        )
        return self.decorate_room(updated)

    def delete_group(self, cid: str) -> None:
        self.conversations.rooms.delete_group(cid)

    def get_group(self, cid: str) -> dict:
        return self.decorate_room(self.conversations.rooms.get_group(cid))

    def decorate_room(self, row: dict) -> dict:
        participants = list(row.get("participant_role_ids") or [])
        briefs = [self._role_brief(rid) for rid in participants]
        out = dict(row)
        out["participant_names"] = [b["name"] for b in briefs]
        out["participants"] = briefs
        if "avatar" not in out:
            out["avatar"] = None
        if "last_active_at" not in out:
            info = self.conversations.rooms.last_activity_for_ids([out["id"]]).get(
                out["id"]
            ) or {}
            out["last_active_at"] = info.get("last_active_at") or None
            out["last_reply_preview"] = info.get("preview") or ""
        else:
            out.setdefault("last_reply_preview", "")
        return out

    def list_groups(self) -> list[dict]:
        rows = self.conversations.rooms.list_groups()
        activity = self.conversations.rooms.last_activity_for_ids(
            [str(r.get("id") or "") for r in rows]
        )
        out: list[dict] = []
        for row in rows:
            info = activity.get(str(row.get("id") or "")) or {}
            out.append(
                self.decorate_room(
                    {
                        **row,
                        "last_active_at": info.get("last_active_at") or None,
                        "last_reply_preview": info.get("preview") or "",
                    }
                )
            )
        return out

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
            "assignments": self._assignment_status(room_id, kind),
        }

    def _assignment_status(self, room_id: str, kind: str) -> list[dict]:
        if kind != KIND_GROUP:
            return []
        out: list[dict] = []
        for row in self.assignments.list_active(room_id):
            out.append(
                {
                    "id": row.get("id"),
                    "assigner_role_id": row.get("assigner_role_id"),
                    "assigner_name": self._role_name(str(row.get("assigner_role_id") or "")),
                    "assignee_role_id": row.get("assignee_role_id"),
                    "assignee_name": self._role_name(str(row.get("assignee_role_id") or "")),
                    "status": row.get("status"),
                    "due_at": row.get("due_at"),
                    "brief": row.get("brief") or "",
                }
            )
        return out

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
        queue_reasons: list[str] = []
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
                queue_reasons.append(status)
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
            if queue_reasons and all(r == "queued_self" for r in queue_reasons):
                summary = (
                    f"已发送给{names}：已点名，对方将在你说完后开始。"
                    f"协作房间 conversation://{room_id}"
                )
            elif queue_reasons and all(r == "queued_role" for r in queue_reasons):
                summary = (
                    f"已发送给{names}：已排队（对方正忙）。"
                    f"协作房间 conversation://{room_id}"
                )
            else:
                summary = (
                    f"已发送给{names}：已排队（房间里有人在说）。"
                    f"协作房间 conversation://{room_id}"
                )
        else:
            status = "mixed"
            summary = (
                f"已发送：{len(started)} 人开始工作，{len(queued)} 人排队。"
                f"协作房间 conversation://{room_id}"
            )
        handed_off = bool(expect_reply and (started or queued))
        if handed_off:
            summary = f"{summary} 本回合到此结束，不要再做刚派出去的工作。"
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
            "end_turn": handed_off,
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
        extra_system: str | None = None,
    ) -> str:
        if self.conversations.role_has_running_turn(role_id):
            self.enqueue(
                role_id,
                room_id=room_id,
                message_id=stimulus_message["id"],
                wake_in=wake_in,
                expect_reply=expect_reply,
            )
            return "queued_role"
        if wake_in in ("room", "peer_dm", "room_lead") and self.conversations.room_has_running_turn(
            room_id
        ):
            self.enqueue(
                role_id,
                room_id=room_id,
                message_id=stimulus_message["id"],
                wake_in=wake_in,
                expect_reply=expect_reply,
            )
            speaker = self.conversations.get_responding_role_id(room_id)
            if speaker == from_role_id:
                return "queued_self"
            return "queued_room"
        return self._start_wake(
            role_id,
            stimulus_message=stimulus_message,
            from_role_id=from_role_id,
            room_id=room_id,
            wake_in=wake_in,
            expect_reply=expect_reply,
            extra_system=extra_system,
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
        extra_system: str | None = None,
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
        extra = extra_system
        inbound_id = None
        speaker_kind = str(stimulus_message.get("speaker_kind") or ACTOR_ROLE)
        if wake_in == "owner_dm":
            cid, _ = self.conversations.ensure_active_conversation(
                role_id, idle_hours=self._idle_hours()
            )
            extra = extra or (
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
                extra = extra or _OWNER_IN_ROOM_EXTRA
            elif speaker_kind == ACTOR_SYSTEM or wake_in == "room_lead":
                speaker = (
                    SYSTEM
                    if speaker_kind == ACTOR_SYSTEM
                    else Actor(kind=ACTOR_ROLE, id=from_role_id)
                )
                extra = extra or (
                    _COORDINATOR_OVERDUE_EXTRA
                    if speaker_kind == ACTOR_SYSTEM
                    else _COORDINATOR_RECEIPT_EXTRA
                )
            else:
                speaker = Actor(kind=ACTOR_ROLE, id=from_role_id)
                extra = extra or _WORKER_EXTRA

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
        try:
            if (
                wake_in == "room"
                and self.conversations.rooms.conversation_kind(cid) == KIND_GROUP
            ):
                self.assignments.mark_working(cid, role_id)
        except Exception:
            log.exception("mark assignment working failed role=%s room=%s", role_id, cid)
        return "started"

    def fire_overdue_assignments(self, *, limit: int = 10) -> int:
        claimed = self.assignments.claim_overdue(limit=limit)
        n = 0
        for asg in claimed:
            room_id = str(asg.get("room_id") or "")
            assigner = str(asg.get("assigner_role_id") or "")
            assignee = str(asg.get("assignee_role_id") or "")
            if not room_id or not assigner:
                continue
            name = self._role_name(assignee) if assignee else "同伴"
            try:
                msg = self.post_message(
                    room_id,
                    speaker=SYSTEM,
                    text=(
                        f"「{name}」的任务已超过预期时间，尚未回执。"
                        "请询问进度或改派。"
                    ),
                    speaker_name="系统",
                    hop=0,
                    client_message_id=f"assignment-overdue:{asg.get('id')}",
                )
                self.wake_role(
                    assigner,
                    stimulus_message=msg,
                    from_role_id="",
                    room_id=room_id,
                    wake_in="room_lead",
                    expect_reply=True,
                    extra_system=_COORDINATOR_OVERDUE_EXTRA,
                )
                n += 1
            except Exception:
                log.exception(
                    "overdue assignment wake failed id=%s room=%s",
                    asg.get("id"),
                    room_id,
                )
        return n


def drain_due_inbound(container: Any) -> None:
    delivery = getattr(container, "room_delivery", None)
    if delivery is None:
        return
    try:
        delivery.drain_all(limit=10)
    except Exception:
        log.exception("room inbound drain failed")
    try:
        delivery.fire_overdue_assignments()
    except Exception:
        log.exception("group assignment overdue drain failed")
