from __future__ import annotations

from typing import TYPE_CHECKING

from app.engine.conversation.shared import (
    TurnInProgress,
    dumps_json,
    new_id,
    now_iso,
    title_from_text,
)
from app.engine.role_onboarding import is_onboarding_kickoff_id

if TYPE_CHECKING:
    from app.engine.conversations import ConversationStore


class TurnLifecycle:
    """会话 turn 状态机：begin / finalize 与派生 outbox 挂钩。"""

    def __init__(self, store: ConversationStore):
        self._store = store

    def begin_turn(
        self,
        cid: str,
        user_text: str,
        client_message_id: str,
        observation_allowed: bool = False,
        *,
        user_ts: str | None = None,
        doc_context: list[str] | None = None,
        primary_doc: str | None = None,
        attachments: list[str] | None = None,
        web_enabled: bool | None = None,
        reuse_user_message_id: str | None = None,
        stimulus=None,
    ) -> dict:
        store = self._store
        with store._lock:
            conv_row = store._conversation_row(cid)
            from app.engine.roles import DEFAULT_ROLE_ID
            from app.engine.rooms.schema import KIND_OWNER_DM, ROOM_ROLE_PLACEHOLDER

            try:
                conv_kind = (conv_row["kind"] or KIND_OWNER_DM).strip() or KIND_OWNER_DM
            except (KeyError, IndexError):
                conv_kind = KIND_OWNER_DM
            try:
                home_role = (conv_row["role_id"] or DEFAULT_ROLE_ID).strip() or DEFAULT_ROLE_ID
            except (KeyError, IndexError):
                home_role = DEFAULT_ROLE_ID
            responding_role_id = None
            speaker_kind = "user"
            speaker_id = "owner"
            speaker_name = None
            causation_id = None
            hop = 0
            inbound_reuse = None
            if stimulus is not None:
                responding_role_id = getattr(stimulus, "responding_role_id", None)
                speaker = getattr(stimulus, "speaker", None)
                if speaker is not None:
                    speaker_kind = speaker.kind
                    speaker_id = speaker.id
                speaker_name = getattr(stimulus, "speaker_name", None)
                causation_id = getattr(stimulus, "causation_id", None)
                hop = int(getattr(stimulus, "hop", 0) or 0)
                inbound_reuse = getattr(stimulus, "inbound_message_id", None)
            if not responding_role_id:
                responding_role_id = (
                    home_role if home_role != ROOM_ROLE_PLACEHOLDER else DEFAULT_ROLE_ID
                )

            existing = store.conn.execute(
                "SELECT * FROM turns WHERE conversation_id = ? AND client_message_id = ?",
                (cid, client_message_id),
            ).fetchone()
            if existing is not None:
                if existing["status"] == "running":
                    raise TurnInProgress(existing["id"])
                user_row = store.conn.execute(
                    "SELECT * FROM messages WHERE id = ?",
                    (existing["user_message_id"],),
                ).fetchone()
                result: dict = {
                    "turn_id": existing["id"],
                    "status": existing["status"],
                    "user_message": store._message_row_to_dict(user_row),
                }
                if existing["assistant_message_id"]:
                    assistant_row = store.conn.execute(
                        "SELECT * FROM messages WHERE id = ?",
                        (existing["assistant_message_id"],),
                    ).fetchone()
                    if assistant_row is not None:
                        result["assistant_message"] = store._message_row_to_dict(
                            assistant_row
                        )
                return result

            if conv_row["active_turn_id"]:
                active_turn = store.conn.execute(
                    "SELECT * FROM turns WHERE id = ?",
                    (conv_row["active_turn_id"],),
                ).fetchone()
                if active_turn is not None and active_turn["status"] == "running":
                    raise TurnInProgress(active_turn["id"])

            if reuse_user_message_id:
                msg_id = self._prepare_reuse_user_message(
                    cid, reuse_user_message_id, user_text
                )
            elif inbound_reuse:
                exist_in = store.conn.execute(
                    "SELECT id FROM messages WHERE id = ? AND conversation_id = ?",
                    (inbound_reuse, cid),
                ).fetchone()
                if exist_in is None:
                    raise ValueError("inbound_message_id not found")
                msg_id = inbound_reuse
            else:
                now = user_ts or now_iso()
                msg_id = new_id()
                seq = store._next_seq(cid)
                raw_text = (
                    stimulus.text if stimulus is not None else user_text
                )
                store.conn.execute(
                    """
                    INSERT INTO messages(
                        id, conversation_id, seq, role, text, ts, status,
                        client_message_id, doc_context_json, attachments_json,
                        primary_doc, web_enabled, speaker_kind, speaker_id,
                        speaker_name, causation_id, hop
                    ) VALUES (?, ?, ?, 'user', ?, ?, 'complete', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        msg_id,
                        cid,
                        seq,
                        raw_text,
                        now,
                        client_message_id,
                        dumps_json(doc_context),
                        dumps_json(attachments),
                        primary_doc,
                        None if web_enabled is None else int(bool(web_enabled)),
                        speaker_kind,
                        speaker_id,
                        speaker_name,
                        causation_id,
                        hop,
                    ),
                )

            turn_id = new_id()
            started_at = now_iso()
            store.conn.execute(
                """
                INSERT INTO turns(
                    id, conversation_id, client_message_id, user_message_id,
                    assistant_message_id, status, observation_allowed,
                    started_at, responding_role_id
                ) VALUES (?, ?, ?, ?, NULL, 'running', ?, ?, ?)
                """,
                (
                    turn_id,
                    cid,
                    client_message_id,
                    msg_id,
                    int(observation_allowed),
                    started_at,
                    responding_role_id,
                ),
            )

            kickoff = is_onboarding_kickoff_id(client_message_id)
            if not reuse_user_message_id and not inbound_reuse and not kickoff:
                store._enqueue_index_jobs(msg_id, turn_id)
            origin = "web"
            try:
                origin = (conv_row["origin"] or "web").strip() or "web"
            except (KeyError, IndexError):
                origin = "web"
            # 通道会话、同伴房间不抽主人画像；主人 tip 仍打 dirty
            from app.engine.channel_plugins.types import is_channel_origin

            if (
                not is_channel_origin(origin)
                and conv_kind == KIND_OWNER_DM
                and speaker_kind == "user"
                and not kickoff
            ):
                store.memory_schedule.mark_dirty_unlocked(cid, at=started_at)
            store._mark_dirty_and_stale(cid)

            title = conv_row["title"]
            if (
                conv_kind == KIND_OWNER_DM
                and title == "新对话"
                and user_text.strip()
                and not kickoff
                and speaker_kind == "user"
            ):
                store.conn.execute(
                    "UPDATE conversations SET title = ? WHERE id = ?",
                    (title_from_text(user_text), cid),
                )

            store.conn.execute(
                "UPDATE conversations SET active_turn_id = ?, updated_at = ? WHERE id = ?",
                (turn_id, started_at, cid),
            )
            store.conn.commit()

            msg_row = store.conn.execute(
                "SELECT * FROM messages WHERE id = ?", (msg_id,)
            ).fetchone()
            return {
                "turn_id": turn_id,
                "status": "running",
                "user_message": store._message_row_to_dict(msg_row),
            }

    def _prepare_reuse_user_message(
        self, cid: str, reuse_user_message_id: str, user_text: str
    ) -> str:
        """删除该用户消息之后的内容与旧 turn，供原地重新回复。须已持 store._lock。"""
        store = self._store
        user_row = store.conn.execute(
            "SELECT * FROM messages WHERE id = ? AND conversation_id = ?",
            (reuse_user_message_id, cid),
        ).fetchone()
        if user_row is None:
            raise ValueError("reuse_user_message_id not found")
        if user_row["role"] != "user":
            raise ValueError("reuse_user_message_id must be a user message")

        # 不允许跨过后续真实用户轮次重生（inject 可随尾部一并清掉）
        later_user = store.conn.execute(
            """
            SELECT id, client_message_id FROM messages
            WHERE conversation_id = ? AND seq > ? AND role = 'user'
            ORDER BY seq ASC
            """,
            (cid, user_row["seq"]),
        ).fetchall()
        for row in later_user:
            cid_key = row["client_message_id"] or ""
            if not str(cid_key).startswith("inject:"):
                raise ValueError(
                    "reuse_user_message_id is not the latest user turn"
                )

        old_turns = store.conn.execute(
            """
            SELECT id, status, assistant_message_id FROM turns
            WHERE conversation_id = ? AND user_message_id = ?
            """,
            (cid, reuse_user_message_id),
        ).fetchall()
        for t in old_turns:
            if t["status"] == "running":
                raise TurnInProgress(t["id"])

        store.conn.execute(
            "DELETE FROM messages WHERE conversation_id = ? AND seq > ?",
            (cid, user_row["seq"]),
        )
        store.conn.execute(
            "DELETE FROM turns WHERE conversation_id = ? AND user_message_id = ?",
            (cid, reuse_user_message_id),
        )

        # 正文以库内为准；请求里的 text 仅作校验提示，不覆盖
        _ = user_text
        return reuse_user_message_id

    def finalize_turn(self, cid: str, turn_id: str, assistant: dict) -> dict | None:
        store = self._store
        with store._lock:
            store._conversation_row(cid)
            turn = store.conn.execute(
                "SELECT * FROM turns WHERE id = ? AND conversation_id = ?",
                (turn_id, cid),
            ).fetchone()
            if turn is None:
                raise KeyError(turn_id)

            if turn["status"] != "running":
                if turn["assistant_message_id"]:
                    msg_row = store.conn.execute(
                        "SELECT * FROM messages WHERE id = ?",
                        (turn["assistant_message_id"],),
                    ).fetchone()
                    if msg_row is not None:
                        return store._message_row_to_dict(msg_row)
                return None

            status = assistant.get("status") or "complete"
            has_content = bool(
                assistant.get("text")
                or assistant.get("timeline")
                or assistant.get("sources")
                or assistant.get("error")
            )

            assistant_msg_id = None
            result: dict | None = None
            if has_content:
                assistant_msg_id = new_id()
                seq = store._next_seq(cid)
                now = assistant.get("ts") or now_iso()
                try:
                    responding = (turn["responding_role_id"] or "").strip()
                except (KeyError, IndexError):
                    responding = ""
                store.conn.execute(
                    """
                    INSERT INTO messages(
                        id, conversation_id, seq, role, text, ts, status,
                        in_reply_to_message_id, timeline_json, sources_json,
                        total_duration_ms, model_name, model_failover,
                        attachments_json, speaker_kind, speaker_id,
                        prompt_tokens, completion_tokens
                    ) VALUES (?, ?, ?, 'assistant', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'role', ?, ?, ?)
                    """,
                    (
                        assistant_msg_id,
                        cid,
                        seq,
                        assistant.get("text") or "",
                        now,
                        status,
                        turn["user_message_id"],
                        dumps_json(assistant.get("timeline", [])),
                        dumps_json(assistant.get("sources", [])),
                        assistant.get("total_duration_ms"),
                        assistant.get("model_name"),
                        1 if assistant.get("model_failover") else 0,
                        dumps_json(assistant.get("attachments"))
                        if assistant.get("attachments")
                        else None,
                        responding or None,
                        assistant.get("prompt_tokens"),
                        assistant.get("completion_tokens"),
                    ),
                )
                store._enqueue_index_jobs(assistant_msg_id, turn_id)
                msg_row = store.conn.execute(
                    "SELECT * FROM messages WHERE id = ?", (assistant_msg_id,)
                ).fetchone()
                result = store._message_row_to_dict(msg_row)

            turn_status = "complete" if status == "complete" else "interrupted"
            finalized_at = now_iso()
            # 兼容：若仍有历史 blocked observe_memory，按 observation_allowed 激活/取消
            store._activate_observe_jobs(
                turn_id, observation_allowed=False
            )
            store.conn.execute(
                """
                UPDATE turns SET assistant_message_id = ?, status = ?, finalized_at = ?
                WHERE id = ?
                """,
                (assistant_msg_id, turn_status, finalized_at, turn_id),
            )
            store.conn.execute(
                "UPDATE conversations SET active_turn_id = NULL, updated_at = ? WHERE id = ?",
                (finalized_at, cid),
            )
            store.conn.commit()
            return result


__all__ = ["TurnLifecycle"]
