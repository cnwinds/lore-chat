"""会话消息图：append / inject / ask_user 决议补丁。"""

from __future__ import annotations

from app.engine.conversation.shared import dumps_json as _dumps
from app.engine.conversation.shared import loads_json as _loads
from app.engine.conversation.shared import new_id as _new_id
from app.engine.conversation.shared import now_iso as _now


def patch_timeline_choice_resolved(
    blocks: list, question_id: str, choice_label: str
) -> bool:
    """递归标记 ask_user / sandbox_run 征询块已选择。返回是否有改动。"""
    changed = False
    for block in blocks:
        if (
            block.get("type") == "tool"
            and block.get("tool") in ("ask_user", "sandbox_run")
            and block.get("question_id") == question_id
        ):
            block["choice_resolved"] = choice_label
            changed = True
        elif block.get("type") == "parallel":
            if patch_timeline_choice_resolved(
                block.get("children", []), question_id, choice_label
            ):
                changed = True
    return changed


class ConversationMessageGraph:
    """消息序、mid-turn inject、timeline 决议补丁。"""

    def __init__(self, store) -> None:
        self.store = store

    def append_messages(self, cid: str, messages: list[dict]) -> dict:
        store = self.store
        with store._lock:
            store._conversation_row(cid)
            now = _now()
            for m in messages:
                seq = store._next_seq(cid)
                store.conn.execute(
                    """
                    INSERT INTO messages(
                        id, conversation_id, seq, role, text, ts, status,
                        timeline_json, sources_json, total_duration_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, 'complete', ?, ?, ?)
                    """,
                    (
                        _new_id(),
                        cid,
                        seq,
                        m.get("role", "assistant"),
                        m.get("text", ""),
                        m.get("ts") or now,
                        _dumps(m.get("timeline")) if "timeline" in m else None,
                        _dumps(m.get("sources")) if "sources" in m else None,
                        m.get("total_duration_ms"),
                    ),
                )
            store.conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, cid)
            )
            store.conn.commit()
            return store._conv_to_dict(store._conversation_row(cid))

    def append_injected_user_message(
        self,
        cid: str,
        *,
        text: str,
        client_message_id: str,
        doc_context: list | None = None,
        primary_doc: str | None = None,
        attachments: list[str] | None = None,
    ) -> dict:
        store = self.store
        with store._lock:
            store._conversation_row(cid)
            msg_id = _new_id()
            seq = store._next_seq(cid)
            now = _now()
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
                    text,
                    now,
                    client_message_id,
                    _dumps(doc_context),
                    _dumps(attachments),
                    primary_doc,
                ),
            )
            store.conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, cid)
            )
            store.conn.commit()
            row = store.conn.execute(
                "SELECT * FROM messages WHERE id = ?", (msg_id,)
            ).fetchone()
            return store._message_row_to_dict(row)

    def mark_question_resolved(
        self, cid: str, question_id: str, choice_label: str
    ) -> None:
        store = self.store
        with store._lock:
            try:
                store._conversation_row(cid)
            except KeyError:
                return
            rows = store.conn.execute(
                """
                SELECT id, timeline_json FROM messages
                WHERE conversation_id = ? AND timeline_json IS NOT NULL
                """,
                (cid,),
            ).fetchall()
            changed = False
            for row in rows:
                timeline = _loads(row["timeline_json"], [])
                if patch_timeline_choice_resolved(timeline, question_id, choice_label):
                    changed = True
                    store.conn.execute(
                        "UPDATE messages SET timeline_json = ? WHERE id = ?",
                        (_dumps(timeline), row["id"]),
                    )
            if changed:
                store.conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (_now(), cid),
                )
                store.conn.commit()
