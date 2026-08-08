"""记忆抽取调度：dirty / CAS / idle / session_observe 入队。

从 ConversationStore 切出的 deep module；SessionMemoryObserve 经此 seam 调度。
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from app.engine.conversation.outbox import DerivationOutbox
from app.engine.conversation.shared import now_iso as _now


class MemoryExtractSchedule:
    """会话级记忆抽取的调度与 CAS（不含对话正文读写）。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        lock: threading.Lock,
        outbox: DerivationOutbox,
    ) -> None:
        self.conn = conn
        self._lock = lock
        self._outbox = outbox

    @staticmethod
    def _bump_cas_timestamp(prev: str) -> str:
        try:
            dt = datetime.fromisoformat(prev)
        except ValueError:
            return _now()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt + timedelta(microseconds=1)).isoformat(timespec="microseconds")

    @classmethod
    def _ensure_cas_advances(cls, prev: str, ts: str) -> str:
        if not prev:
            return ts
        try:
            dt_prev = datetime.fromisoformat(prev)
            dt_ts = datetime.fromisoformat(ts)
        except ValueError:
            return cls._bump_cas_timestamp(prev) if ts == prev else ts
        if dt_ts <= dt_prev:
            return cls._bump_cas_timestamp(prev)
        return ts

    def mark_dirty_unlocked(self, cid: str, *, at: str | None = None) -> None:
        ts = at or _now()
        row = self.conn.execute(
            "SELECT last_user_message_at FROM conversations WHERE id = ?",
            (cid,),
        ).fetchone()
        prev = (row["last_user_message_at"] if row else None) or ""
        if prev:
            ts = self._ensure_cas_advances(prev, ts)
        self.conn.execute(
            """
            UPDATE conversations
            SET memory_dirty = 1, last_user_message_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (ts, ts, cid),
        )
        self._outbox.cancel_session_observe(cid)

    def mark_dirty(self, cid: str, *, at: str | None = None) -> None:
        with self._lock:
            self.mark_dirty_unlocked(cid, at=at)
            self.conn.commit()

    def get_last_user_message_at(self, cid: str) -> str | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT last_user_message_at FROM conversations WHERE id = ?",
                (cid,),
            ).fetchone()
            if not row:
                return None
            return row["last_user_message_at"]

    def clear_dirty(
        self,
        cid: str,
        *,
        at: str | None = None,
        expected_last_user_message_at: str | None = None,
    ) -> int | None:
        """成功抽取后清 dirty，并递增 memory_extract_revision。

        CAS：若传入 expected_last_user_message_at，仅当时间戳未变才清 dirty。
        成功返回新 revision；CAS 失败返回 None。
        """
        ts = at or _now()
        with self._lock:
            if expected_last_user_message_at is not None:
                cur = self.conn.execute(
                    """
                    UPDATE conversations
                    SET memory_dirty = 0,
                        last_memory_extract_at = ?,
                        memory_extract_revision = memory_extract_revision + 1,
                        updated_at = ?
                    WHERE id = ?
                      AND last_user_message_at IS ?
                    """,
                    (ts, ts, cid, expected_last_user_message_at),
                )
                if cur.rowcount == 0:
                    self.conn.commit()
                    return None
            else:
                self.conn.execute(
                    """
                    UPDATE conversations
                    SET memory_dirty = 0,
                        last_memory_extract_at = ?,
                        memory_extract_revision = memory_extract_revision + 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (ts, ts, cid),
                )
            row = self.conn.execute(
                "SELECT memory_extract_revision FROM conversations WHERE id = ?",
                (cid,),
            ).fetchone()
            self.conn.commit()
            return int(row["memory_extract_revision"]) if row else 0

    def get_extract_revision(self, cid: str) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT memory_extract_revision FROM conversations WHERE id = ?",
                (cid,),
            ).fetchone()
            if not row:
                return 0
            return int(row["memory_extract_revision"] or 0)

    def enqueue_session_observe_unlocked(
        self, conversation_id: str, *, immediate: bool = False
    ) -> bool:
        return self._outbox.enqueue_session_observe(
            conversation_id, immediate=immediate
        )

    def enqueue_session_observe(
        self, conversation_id: str, *, immediate: bool = False
    ) -> bool:
        with self._lock:
            ok = self.enqueue_session_observe_unlocked(
                conversation_id, immediate=immediate
            )
            self.conn.commit()
            return ok

    def batch_mark_dirty_and_enqueue(
        self,
        conversation_ids: list[str],
        *,
        mark_dirty: bool = True,
        immediate: bool = False,
    ) -> int:
        with self._lock:
            n = 0
            for cid in conversation_ids:
                if mark_dirty:
                    self.mark_dirty_unlocked(cid)
                if self.enqueue_session_observe_unlocked(cid, immediate=immediate):
                    n += 1
            self.conn.commit()
            return n

    def cancel_legacy_observe_memory(self) -> int:
        with self._lock:
            n = self._outbox.cancel_legacy_observe_memory()
            self.conn.commit()
            return n

    def is_extract_idle(self, cid: str, *, idle_hours: float = 24.0) -> bool:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT memory_dirty, last_user_message_at
                FROM conversations WHERE id = ?
                """,
                (cid,),
            ).fetchone()
        if not row or not row["memory_dirty"]:
            return False
        ts = row["last_user_message_at"]
        if not ts:
            return False
        try:
            last = datetime.fromisoformat(ts)
        except ValueError:
            return False
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - last >= timedelta(hours=idle_hours)

    def request_immediate_unlocked(
        self, cid: str, *, at: str | None = None
    ) -> bool:
        self.mark_dirty_unlocked(cid, at=at)
        ok = self.enqueue_session_observe_unlocked(cid, immediate=True)
        if not ok:
            self.conn.execute(
                """
                UPDATE conversations
                SET memory_immediate_pending = 1, updated_at = ?
                WHERE id = ?
                """,
                (at or _now(), cid),
            )
        return ok

    def request_immediate(self, cid: str) -> bool:
        with self._lock:
            ok = self.request_immediate_unlocked(cid)
            self.conn.commit()
            return ok

    def consume_immediate_pending(self, cid: str) -> bool:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT memory_immediate_pending
                FROM conversations WHERE id = ?
                """,
                (cid,),
            ).fetchone()
            if not row or not int(row["memory_immediate_pending"] or 0):
                return False
            self.conn.execute(
                """
                UPDATE conversations
                SET memory_immediate_pending = 0, updated_at = ?
                WHERE id = ?
                """,
                (_now(), cid),
            )
            self.conn.commit()
            return True

    def list_idle_dirty(
        self, *, idle_hours: float = 24.0, limit: int = 20
    ) -> list[dict]:
        def _parse(ts: str) -> datetime | None:
            try:
                dt = datetime.fromisoformat(ts)
            except ValueError:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt

        now = datetime.now(timezone.utc)
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT id, last_user_message_at, memory_dirty
                FROM conversations
                WHERE memory_dirty = 1
                  AND last_user_message_at IS NOT NULL
                ORDER BY last_user_message_at ASC
                """
            ).fetchall()
        out: list[dict] = []
        for r in rows:
            last = _parse(r["last_user_message_at"] or "")
            if last is None:
                continue
            if now - last.astimezone(timezone.utc) >= timedelta(hours=idle_hours):
                out.append(dict(r))
            if len(out) >= limit:
                break
        return out


__all__ = ["MemoryExtractSchedule"]
