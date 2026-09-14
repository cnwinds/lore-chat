"""群内派工账本：开账 / 结账 / 逾期。与 ConversationStore 共用 conn/lock。"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from app.engine.conversation.shared import new_id, now_iso
from app.time import now_display

if TYPE_CHECKING:
    from app.engine.conversations import ConversationStore

STATUS_OPEN = "open"
STATUS_WORKING = "working"
STATUS_DONE = "done"
STATUS_OVERDUE = "overdue"


def _due_at_from_now(minutes: int | None) -> str | None:
    if minutes is None:
        return None
    n = max(1, int(minutes))
    return (now_display() + timedelta(minutes=n)).isoformat(timespec="seconds")


class GroupAssignmentLedger:
    def __init__(self, conversations: ConversationStore) -> None:
        self._store = conversations

    def open(
        self,
        *,
        room_id: str,
        assigner_role_id: str,
        assignee_role_id: str,
        source_message_id: str | None,
        brief: str = "",
        due_in_minutes: int | None = None,
    ) -> dict:
        store = self._store
        aid = new_id()
        now = now_iso()
        clip = (brief or "").strip()[:200]
        with store._lock:
            store.conn.execute(
                """
                INSERT INTO group_assignments(
                    id, room_id, assigner_role_id, assignee_role_id,
                    source_message_id, brief, due_in_minutes, due_at,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    aid,
                    room_id,
                    assigner_role_id,
                    assignee_role_id,
                    source_message_id,
                    clip,
                    due_in_minutes,
                    STATUS_OPEN,
                    now,
                ),
            )
            store.conn.commit()
        return {
            "id": aid,
            "room_id": room_id,
            "assigner_role_id": assigner_role_id,
            "assignee_role_id": assignee_role_id,
            "source_message_id": source_message_id,
            "brief": clip,
            "due_in_minutes": due_in_minutes,
            "due_at": None,
            "status": STATUS_OPEN,
            "created_at": now,
        }

    def mark_working(self, room_id: str, assignee_role_id: str) -> None:
        store = self._store
        now = now_iso()
        with store._lock:
            rows = store.conn.execute(
                """
                SELECT id, due_in_minutes FROM group_assignments
                WHERE room_id = ? AND assignee_role_id = ? AND status = ?
                """,
                (room_id, assignee_role_id, STATUS_OPEN),
            ).fetchall()
            for row in rows:
                minutes = row["due_in_minutes"]
                due_at = _due_at_from_now(int(minutes) if minutes is not None else None)
                store.conn.execute(
                    """
                    UPDATE group_assignments
                    SET status = ?, due_at = ?
                    WHERE id = ?
                    """,
                    (STATUS_WORKING, due_at, row["id"]),
                )
            if rows:
                store.conn.commit()

    def close_oldest_open(
        self,
        *,
        room_id: str,
        assignee_role_id: str,
        receipt_message_id: str | None,
    ) -> dict | None:
        """结清该工人在本群最早一笔未完成账（含已超时尚未回执）。"""
        store = self._store
        with store._lock:
            row = store.conn.execute(
                """
                SELECT * FROM group_assignments
                WHERE room_id = ? AND assignee_role_id = ? AND status IN (?, ?, ?)
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (
                    room_id,
                    assignee_role_id,
                    STATUS_OPEN,
                    STATUS_WORKING,
                    STATUS_OVERDUE,
                ),
            ).fetchone()
            if row is None:
                return None
            store.conn.execute(
                """
                UPDATE group_assignments
                SET status = ?, receipt_message_id = ?
                WHERE id = ?
                """,
                (STATUS_DONE, receipt_message_id, row["id"]),
            )
            store.conn.commit()
            data = dict(row)
            data["status"] = STATUS_DONE
            data["receipt_message_id"] = receipt_message_id
            return data

    def list_active(self, room_id: str) -> list[dict]:
        store = self._store
        with store._lock:
            rows = store.conn.execute(
                """
                SELECT * FROM group_assignments
                WHERE room_id = ? AND status IN (?, ?, ?)
                ORDER BY created_at ASC
                """,
                (room_id, STATUS_OPEN, STATUS_WORKING, STATUS_OVERDUE),
            ).fetchall()
            return [dict(r) for r in rows]

    def claim_overdue(self, *, now: str | None = None, limit: int = 10) -> list[dict]:
        """把到期未结账标成 overdue，并记下 inquired_at，避免刷屏。"""
        store = self._store
        stamp = now or now_iso()
        with store._lock:
            rows = store.conn.execute(
                """
                SELECT * FROM group_assignments
                WHERE status IN (?, ?)
                  AND due_at IS NOT NULL AND due_at <= ?
                  AND inquired_at IS NULL
                ORDER BY due_at ASC
                LIMIT ?
                """,
                (STATUS_OPEN, STATUS_WORKING, stamp, limit),
            ).fetchall()
            claimed: list[dict] = []
            for row in rows:
                store.conn.execute(
                    """
                    UPDATE group_assignments
                    SET status = ?, inquired_at = ?
                    WHERE id = ?
                    """,
                    (STATUS_OVERDUE, stamp, row["id"]),
                )
                data = dict(row)
                data["status"] = STATUS_OVERDUE
                data["inquired_at"] = stamp
                claimed.append(data)
            if claimed:
                store.conn.commit()
            return claimed
