from __future__ import annotations

from typing import TYPE_CHECKING

from app.engine.conversation.shared import (
    TurnInProgress,
    dumps_json,
    new_id,
    now_iso,
    title_from_text,
)

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
    ) -> dict:
        store = self._store
        with store._lock:
            conv_row = store._conversation_row(cid)

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

            now = user_ts or now_iso()
            msg_id = new_id()
            seq = store._next_seq(cid)
            store.conn.execute(
                """
                INSERT INTO messages(
                    id, conversation_id, seq, role, text, ts, status,
                    client_message_id, doc_context_json, attachments_json, primary_doc
                ) VALUES (?, ?, ?, 'user', ?, ?, 'complete', ?, ?, ?, ?)
                """,
                (
                    msg_id,
                    cid,
                    seq,
                    user_text,
                    now,
                    client_message_id,
                    dumps_json(doc_context),
                    dumps_json(attachments),
                    primary_doc,
                ),
            )

            turn_id = new_id()
            started_at = now_iso()
            store.conn.execute(
                """
                INSERT INTO turns(
                    id, conversation_id, client_message_id, user_message_id,
                    assistant_message_id, status, observation_allowed,
                    started_at
                ) VALUES (?, ?, ?, ?, NULL, 'running', ?, ?)
                """,
                (turn_id, cid, client_message_id, msg_id, int(observation_allowed), started_at),
            )

            store._enqueue_index_jobs(msg_id, turn_id)
            store._enqueue_observe_memory(msg_id, turn_id)
            store._mark_dirty_and_stale(cid)

            title = conv_row["title"]
            if title == "新对话" and user_text.strip():
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
                store.conn.execute(
                    """
                    INSERT INTO messages(
                        id, conversation_id, seq, role, text, ts, status,
                        in_reply_to_message_id, timeline_json, sources_json,
                        total_duration_ms
                    ) VALUES (?, ?, ?, 'assistant', ?, ?, ?, ?, ?, ?, ?)
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
                    ),
                )
                store._enqueue_index_jobs(assistant_msg_id, turn_id)
                msg_row = store.conn.execute(
                    "SELECT * FROM messages WHERE id = ?", (assistant_msg_id,)
                ).fetchone()
                result = store._message_row_to_dict(msg_row)

            turn_status = "complete" if status == "complete" else "interrupted"
            finalized_at = now_iso()
            store._activate_observe_jobs(
                turn_id, observation_allowed=bool(turn["observation_allowed"])
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
