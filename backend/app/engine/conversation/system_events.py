"""会话系统事件流（memory_updated / memory_decayed 等）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.engine.conversation.shared import dumps_json as _dumps
from app.engine.conversation.shared import loads_json as _loads
from app.engine.conversation.shared import new_id as _new_id
from app.engine.conversation.shared import now_iso as _now

if TYPE_CHECKING:
    from app.engine.conversations import ConversationStore


class ConversationSystemEvents:
    def __init__(self, store: ConversationStore) -> None:
        self._store = store

    def append(self, conversation_id: str, event_type: str, payload: dict) -> dict:
        event_id = _new_id()
        created_at = _now()
        with self._store._lock:
            self._store.conn.execute(
                """
                INSERT INTO conversation_system_events(
                    id, conversation_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, conversation_id, event_type, _dumps(payload), created_at),
            )
            self._store.conn.commit()
        return {
            "id": event_id,
            "event_type": event_type,
            "payload": payload,
            "created_at": created_at,
        }

    def list(
        self,
        conversation_id: str,
        *,
        after_event_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        with self._store._lock:
            if after_event_id:
                anchor = self._store.conn.execute(
                    "SELECT rowid FROM conversation_system_events WHERE id = ?",
                    (after_event_id,),
                ).fetchone()
                if anchor is None:
                    return []
                rows = self._store.conn.execute(
                    """
                    SELECT * FROM conversation_system_events
                    WHERE conversation_id = ? AND rowid > ?
                    ORDER BY rowid ASC LIMIT ?
                    """,
                    (conversation_id, anchor["rowid"], limit),
                ).fetchall()
            else:
                rows = self._store.conn.execute(
                    """
                    SELECT * FROM conversation_system_events
                    WHERE conversation_id = ?
                    ORDER BY created_at ASC LIMIT ?
                    """,
                    (conversation_id, limit),
                ).fetchall()
            out = []
            for row in rows:
                out.append(
                    {
                        "id": row["id"],
                        "event_type": row["event_type"],
                        "payload": _loads(row["payload_json"], {}),
                        "created_at": row["created_at"],
                    }
                )
            return out
