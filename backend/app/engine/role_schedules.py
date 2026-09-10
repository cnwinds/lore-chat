"""角色定时任务：按 timing 规格触发，写入该角色活跃线。"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.engine.schedule_timing import (
    interval_hours_for_storage,
    next_run_iso,
    normalize_timing,
    summarize_timing,
    timing_from_row,
)


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
            self._migrate_timing_columns()
            self.conn.commit()

    def _migrate_timing_columns(self) -> None:
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(role_schedules)")}
        if "kind" not in cols:
            self.conn.execute(
                "ALTER TABLE role_schedules ADD COLUMN kind TEXT NOT NULL DEFAULT 'interval'"
            )
        if "spec_json" not in cols:
            self.conn.execute(
                "ALTER TABLE role_schedules ADD COLUMN spec_json TEXT NOT NULL DEFAULT '{}'"
            )
        rows = self.conn.execute(
            "SELECT id, interval_hours, spec_json FROM role_schedules"
        ).fetchall()
        for row in rows:
            raw = row["spec_json"] or ""
            if raw and raw not in ("{}", ""):
                continue
            spec = {
                "kind": "interval",
                "interval_hours": float(row["interval_hours"]),
            }
            self.conn.execute(
                "UPDATE role_schedules SET kind = 'interval', spec_json = ? WHERE id = ?",
                (json.dumps(spec, ensure_ascii=False), row["id"]),
            )

    def _row(self, row: sqlite3.Row) -> dict:
        timing = timing_from_row(row)
        return {
            "id": row["id"],
            "role_id": row["role_id"],
            "prompt": row["prompt"],
            "interval_hours": float(row["interval_hours"]),
            "kind": timing["kind"],
            "timing": timing,
            "timing_summary": summarize_timing(timing),
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

    def get(self, schedule_id: str) -> dict:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM role_schedules WHERE id = ?", (schedule_id,)
            ).fetchone()
            if row is None:
                raise KeyError(schedule_id)
            return self._row(row)

    def create(
        self,
        role_id: str,
        *,
        prompt: str,
        interval_hours: float | None = None,
        timing: dict | None = None,
        enabled: bool = True,
    ) -> dict:
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("定时提示词不能为空")
        spec = normalize_timing(timing, interval_hours=interval_hours)
        hours = interval_hours_for_storage(spec)
        sid = _new_id()
        stamp = _now_iso()
        next_run = next_run_iso(spec) if enabled else None
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO role_schedules(
                    id, role_id, prompt, interval_hours, enabled,
                    next_run_at, last_run_at, created_at, updated_at,
                    kind, spec_json
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
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
                    spec["kind"],
                    json.dumps(spec, ensure_ascii=False),
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
        timing: dict | None = None,
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
            current = timing_from_row(row)
            if timing is not None:
                spec = normalize_timing(timing, interval_hours=interval_hours)
            elif interval_hours is not None:
                spec = normalize_timing(
                    {"kind": "interval", "interval_hours": interval_hours}
                )
            else:
                spec = current
            hours = interval_hours_for_storage(spec)
            new_enabled = (
                bool(row["enabled"]) if enabled is None else bool(enabled)
            )
            timing_changed = spec != current
            next_run = row["next_run_at"]
            if not new_enabled:
                next_run = None
            elif timing_changed or (enabled is True and not row["enabled"]):
                next_run = next_run_iso(spec)
            stamp = _now_iso()
            self.conn.execute(
                """
                UPDATE role_schedules
                SET prompt = ?, interval_hours = ?, enabled = ?,
                    next_run_at = ?, updated_at = ?, kind = ?, spec_json = ?
                WHERE id = ?
                """,
                (
                    new_prompt,
                    hours,
                    1 if new_enabled else 0,
                    next_run,
                    stamp,
                    spec["kind"],
                    json.dumps(spec, ensure_ascii=False),
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

    def mark_ran(self, schedule_id: str, *, interval_hours: float | None = None) -> None:
        del interval_hours  # 日历定时按 spec 重算，忽略旧的间隔参数
        stamp = _now_iso()
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM role_schedules WHERE id = ?", (schedule_id,)
            ).fetchone()
            if row is None:
                return
            spec = timing_from_row(row)
            next_run = next_run_iso(spec)
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
