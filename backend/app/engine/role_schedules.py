"""角色定时任务：间隔触发，写入该角色活跃线。"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS role_schedules (
    id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    interval_hours REAL NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    next_run_at TEXT,
    last_run_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_role_schedules_next
    ON role_schedules(enabled, next_run_at);
"""


class RoleScheduleStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock):
        self.conn = conn
        self._lock = lock
        with self._lock:
            self.conn.executescript(_SCHEMA)
            self.conn.commit()

    def _row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "role_id": row["role_id"],
            "prompt": row["prompt"],
            "interval_hours": float(row["interval_hours"]),
            "enabled": bool(row["enabled"]),
            "next_run_at": row["next_run_at"],
            "last_run_at": row["last_run_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_for_role(self, role_id: str) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM role_schedules WHERE role_id = ? ORDER BY created_at",
                (role_id,),
            ).fetchall()
            return [self._row(r) for r in rows]

    def create(
        self,
        role_id: str,
        *,
        prompt: str,
        interval_hours: float,
        enabled: bool = True,
    ) -> dict:
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("定时提示词不能为空")
        hours = float(interval_hours)
        if hours < 0.5:
            raise ValueError("间隔至少 0.5 小时")
        sid = _new_id()
        stamp = _now_iso()
        next_run = (_now() + timedelta(hours=hours)).isoformat()
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO role_schedules(
                    id, role_id, prompt, interval_hours, enabled,
                    next_run_at, last_run_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    sid,
                    role_id,
                    prompt,
                    hours,
                    1 if enabled else 0,
                    next_run,
                    stamp,
                    stamp,
                ),
            )
            self.conn.commit()
            row = self.conn.execute(
                "SELECT * FROM role_schedules WHERE id = ?", (sid,)
            ).fetchone()
            assert row is not None
            return self._row(row)

    def update(
        self,
        schedule_id: str,
        *,
        prompt: str | None = None,
        interval_hours: float | None = None,
        enabled: bool | None = None,
    ) -> dict:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM role_schedules WHERE id = ?", (schedule_id,)
            ).fetchone()
            if row is None:
                raise KeyError(schedule_id)
            new_prompt = row["prompt"] if prompt is None else prompt.strip()
            if not new_prompt:
                raise ValueError("定时提示词不能为空")
            new_hours = (
                float(row["interval_hours"])
                if interval_hours is None
                else float(interval_hours)
            )
            if new_hours < 0.5:
                raise ValueError("间隔至少 0.5 小时")
            new_enabled = (
                bool(row["enabled"]) if enabled is None else bool(enabled)
            )
            next_run = row["next_run_at"]
            if interval_hours is not None or (enabled is True and not row["enabled"]):
                next_run = (_now() + timedelta(hours=new_hours)).isoformat()
            stamp = _now_iso()
            self.conn.execute(
                """
                UPDATE role_schedules
                SET prompt = ?, interval_hours = ?, enabled = ?,
                    next_run_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    new_prompt,
                    new_hours,
                    1 if new_enabled else 0,
                    next_run,
                    stamp,
                    schedule_id,
                ),
            )
            self.conn.commit()
            updated = self.conn.execute(
                "SELECT * FROM role_schedules WHERE id = ?", (schedule_id,)
            ).fetchone()
            assert updated is not None
            return self._row(updated)

    def delete(self, schedule_id: str) -> None:
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM role_schedules WHERE id = ?", (schedule_id,)
            )
            self.conn.commit()
            if cur.rowcount == 0:
                raise KeyError(schedule_id)

    def delete_for_role(self, role_id: str) -> None:
        with self._lock:
            self.conn.execute(
                "DELETE FROM role_schedules WHERE role_id = ?", (role_id,)
            )
            self.conn.commit()

    def list_due(self, *, limit: int = 20) -> list[dict]:
        now = _now_iso()
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM role_schedules
                WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ?
                ORDER BY next_run_at ASC
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()
            return [self._row(r) for r in rows]

    def mark_ran(self, schedule_id: str, *, interval_hours: float) -> None:
        stamp = _now_iso()
        next_run = (_now() + timedelta(hours=float(interval_hours))).isoformat()
        with self._lock:
            self.conn.execute(
                """
                UPDATE role_schedules
                SET last_run_at = ?, next_run_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (stamp, next_run, stamp, schedule_id),
            )
            self.conn.commit()

    def defer(self, schedule_id: str, *, minutes: float = 5) -> None:
        """有进行中 turn 时短顺延。"""
        next_run = (_now() + timedelta(minutes=minutes)).isoformat()
        stamp = _now_iso()
        with self._lock:
            self.conn.execute(
                """
                UPDATE role_schedules
                SET next_run_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_run, stamp, schedule_id),
            )
            self.conn.commit()
