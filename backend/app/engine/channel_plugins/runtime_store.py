"""通道运行时落盘：会话映射、event_id 去重、按实例日志。"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS channel_threads (
    instance_id TEXT NOT NULL,
    external_key TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    PRIMARY KEY (instance_id, external_key)
);

CREATE TABLE IF NOT EXISTS event_seen (
    instance_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    PRIMARY KEY (instance_id, event_id)
);

CREATE TABLE IF NOT EXISTS instance_logs (
    id TEXT PRIMARY KEY,
    instance_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    extra TEXT,
    duration_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_event_seen_at ON event_seen(seen_at);
CREATE INDEX IF NOT EXISTS idx_instance_logs_inst_ts
    ON instance_logs(instance_id, ts DESC);
"""

_EVENT_TTL = timedelta(hours=24)
_LOG_KEEP = 1000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChannelRuntimeStore:
    def __init__(self, kb_path: str | Path):
        self._path = Path(kb_path) / ".kb" / "channel_runtime.db"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(_SCHEMA)
            self.conn.commit()

    def close(self) -> None:
        with self._lock:
            if self.conn is not None:
                self.conn.close()
                self.conn = None

    def get_thread(self, instance_id: str, external_key: str) -> str | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT conversation_id FROM channel_threads "
                "WHERE instance_id = ? AND external_key = ?",
                (instance_id, external_key),
            ).fetchone()
        return str(row["conversation_id"]) if row else None

    def put_thread(self, instance_id: str, external_key: str, conversation_id: str) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO channel_threads(instance_id, external_key, conversation_id)
                VALUES (?, ?, ?)
                ON CONFLICT(instance_id, external_key) DO UPDATE SET
                    conversation_id = excluded.conversation_id
                """,
                (instance_id, external_key, conversation_id),
            )
            self.conn.commit()

    def seen_event(self, instance_id: str, event_id: str) -> bool:
        eid = (event_id or "").strip()
        if not eid:
            return False
        self.prune_events()
        with self._lock:
            row = self.conn.execute(
                "SELECT 1 FROM event_seen WHERE instance_id = ? AND event_id = ?",
                (instance_id, eid),
            ).fetchone()
        return row is not None

    def mark_event(self, instance_id: str, event_id: str) -> bool:
        """记录 event_id。已存在则返回 False（重复）。"""
        eid = (event_id or "").strip()
        if not eid:
            return True
        self.prune_events()
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO event_seen(instance_id, event_id, seen_at) VALUES (?, ?, ?)",
                    (instance_id, eid, _now()),
                )
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def prune_events(self) -> int:
        cutoff = (datetime.now(timezone.utc) - _EVENT_TTL).isoformat()
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM event_seen WHERE seen_at < ?", (cutoff,)
            )
            self.conn.commit()
            return cur.rowcount

    def add_log(
        self,
        instance_id: str,
        *,
        kind: str,
        message: str,
        level: str = "info",
        extra: dict[str, Any] | None = None,
        duration_ms: int | None = None,
    ) -> str:
        lid = uuid.uuid4().hex[:16]
        payload = json.dumps(extra, ensure_ascii=False) if extra else None
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO instance_logs(
                    id, instance_id, ts, level, kind, message, extra, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lid,
                    instance_id,
                    _now(),
                    level,
                    kind,
                    message,
                    payload,
                    duration_ms,
                ),
            )
            extra_ids = self.conn.execute(
                """
                SELECT id FROM instance_logs
                WHERE instance_id = ?
                ORDER BY ts DESC
                LIMIT -1 OFFSET ?
                """,
                (instance_id, _LOG_KEEP),
            ).fetchall()
            if extra_ids:
                self.conn.executemany(
                    "DELETE FROM instance_logs WHERE id = ?",
                    [(row["id"],) for row in extra_ids],
                )
            self.conn.commit()
        return lid

    def list_logs(
        self,
        instance_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        cap = max(1, min(int(limit), 200))
        skip = max(0, int(offset))
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM instance_logs
                WHERE instance_id = ?
                ORDER BY ts DESC
                LIMIT ? OFFSET ?
                """,
                (instance_id, cap, skip),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            extra = None
            raw = row["extra"]
            if raw:
                try:
                    extra = json.loads(raw)
                except json.JSONDecodeError:
                    extra = {"raw": raw}
            out.append(
                {
                    "id": row["id"],
                    "instance_id": row["instance_id"],
                    "ts": row["ts"],
                    "level": row["level"],
                    "kind": row["kind"],
                    "message": row["message"],
                    "extra": extra,
                    "duration_ms": row["duration_ms"],
                }
            )
        return out
