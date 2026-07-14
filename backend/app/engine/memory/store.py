from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.engine.memory.constants import ORIGIN_RANK

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS memory_facts (
    id TEXT PRIMARY KEY,
    owner_key TEXT NOT NULL,
    slot_key TEXT NOT NULL,
    category TEXT NOT NULL,
    statement TEXT NOT NULL,
    normalized_value_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    origin TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    sensitivity TEXT NOT NULL DEFAULT 'normal',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    confirmed_at TEXT,
    valid_until TEXT,
    supersedes_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner_key, slot_key, normalized_value_hash)
);

CREATE TABLE IF NOT EXISTS memory_evidence (
    fact_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    start_char INTEGER NOT NULL,
    end_char INTEGER NOT NULL,
    quote_hash TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (fact_id, message_id, start_char, end_char),
    FOREIGN KEY (fact_id) REFERENCES memory_facts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_tombstones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_key TEXT NOT NULL,
    slot_key TEXT NOT NULL,
    blocked_value_hash TEXT,
    reason TEXT NOT NULL,
    forgotten_at TEXT NOT NULL,
    cleared_at TEXT
);

CREATE TABLE IF NOT EXISTS memory_render_state (
    owner_key TEXT PRIMARY KEY,
    revision INTEGER NOT NULL DEFAULT 0,
    file_hash TEXT,
    file_mtime REAL,
    rendered_fact_ids_json TEXT NOT NULL DEFAULT '[]',
    valid_snapshot_body TEXT,
    render_dirty INTEGER NOT NULL DEFAULT 0,
    git_dirty INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS memory_source_barriers (
    conversation_id TEXT NOT NULL,
    deletion_id TEXT NOT NULL,
    deleted_at TEXT NOT NULL,
    PRIMARY KEY (conversation_id, deletion_id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_fact(row: sqlite3.Row) -> dict:
    return dict(row)


class MemoryStore:
    def __init__(self, db_path: str | Path, *, owner_key: str):
        self.db_path = Path(db_path)
        self.owner_key = owner_key
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def upsert_fact(
        self,
        *,
        slot_key: str,
        category: str,
        statement: str,
        normalized_value_hash: str,
        origin: str,
        confidence: float = 1.0,
        sensitivity: str = "normal",
        status: str = "confirmed",
        fact_id: str | None = None,
    ) -> dict:
        now = _now()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM memory_facts
                WHERE owner_key = ? AND slot_key = ? AND normalized_value_hash = ?
                """,
                (self.owner_key, slot_key, normalized_value_hash),
            ).fetchone()
            if existing:
                merged_origin = existing["origin"]
                if ORIGIN_RANK.get(origin, 0) > ORIGIN_RANK.get(existing["origin"], 0):
                    merged_origin = origin
                merged_conf = max(float(existing["confidence"]), float(confidence))
                conn.execute(
                    """
                    UPDATE memory_facts SET
                        statement = ?, category = ?, origin = ?, confidence = ?,
                        sensitivity = ?, status = ?, last_seen_at = ?, updated_at = ?,
                        confirmed_at = COALESCE(confirmed_at, ?)
                    WHERE id = ?
                    """,
                    (
                        statement,
                        category,
                        merged_origin,
                        merged_conf,
                        sensitivity,
                        status,
                        now,
                        now,
                        now if status == "confirmed" else None,
                        existing["id"],
                    ),
                )
                conn.commit()
                return self.get_fact(existing["id"]) or {}

            fid = fact_id or str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO memory_facts (
                    id, owner_key, slot_key, category, statement, normalized_value_hash,
                    status, origin, confidence, sensitivity,
                    first_seen_at, last_seen_at, confirmed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fid,
                    self.owner_key,
                    slot_key,
                    category,
                    statement,
                    normalized_value_hash,
                    status,
                    origin,
                    confidence,
                    sensitivity,
                    now,
                    now,
                    now if status == "confirmed" else None,
                    now,
                    now,
                ),
            )
            conn.commit()
            return self.get_fact(fid) or {}

    def get_fact(self, fact_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_facts WHERE id = ? AND owner_key = ?",
                (fact_id, self.owner_key),
            ).fetchone()
            return _row_to_fact(row) if row else None

    def list_confirmed(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_facts
                WHERE owner_key = ? AND status = 'confirmed'
                ORDER BY updated_at DESC
                """,
                (self.owner_key,),
            ).fetchall()
            return [_row_to_fact(r) for r in rows]

    def mark_forgotten(self, fact_id: str, *, reason: str = "user_forget") -> None:
        now = _now()
        fact = self.get_fact(fact_id)
        if not fact:
            return
        with self._connect() as conn:
            conn.execute(
                "UPDATE memory_facts SET status = 'forgotten', updated_at = ? WHERE id = ?",
                (now, fact_id),
            )
            conn.execute(
                """
                INSERT INTO memory_tombstones (
                    owner_key, slot_key, blocked_value_hash, reason, forgotten_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.owner_key,
                    fact["slot_key"],
                    fact["normalized_value_hash"],
                    reason,
                    now,
                ),
            )
            conn.commit()

    def clear_tombstone(self, *, slot_key: str, normalized_value_hash: str) -> bool:
        now = _now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE memory_tombstones
                SET cleared_at = ?
                WHERE owner_key = ? AND slot_key = ? AND blocked_value_hash = ?
                  AND cleared_at IS NULL
                """,
                (now, self.owner_key, slot_key, normalized_value_hash),
            )
            conn.commit()
            return cur.rowcount > 0

    def has_tombstone(self, *, slot_key: str, normalized_value_hash: str | None = None) -> bool:
        with self._connect() as conn:
            if normalized_value_hash:
                row = conn.execute(
                    """
                    SELECT 1 FROM memory_tombstones
                    WHERE owner_key = ? AND slot_key = ? AND blocked_value_hash = ?
                      AND cleared_at IS NULL
                    LIMIT 1
                    """,
                    (self.owner_key, slot_key, normalized_value_hash),
                ).fetchone()
                return row is not None
            row = conn.execute(
                """
                SELECT 1 FROM memory_tombstones
                WHERE owner_key = ? AND slot_key = ? AND blocked_value_hash IS NULL
                  AND cleared_at IS NULL
                LIMIT 1
                """,
                (self.owner_key, slot_key),
            ).fetchone()
            return row is not None

    def add_evidence(
        self,
        *,
        fact_id: str,
        conversation_id: str,
        message_id: str,
        start_char: int,
        end_char: int,
        quote_hash: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO memory_evidence (
                    fact_id, conversation_id, message_id, start_char, end_char,
                    quote_hash, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact_id,
                    conversation_id,
                    message_id,
                    start_char,
                    end_char,
                    quote_hash,
                    _now(),
                ),
            )
            conn.commit()

    def list_evidence(self, fact_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_evidence WHERE fact_id = ? ORDER BY observed_at",
                (fact_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_render_state(self) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_render_state WHERE owner_key = ?",
                (self.owner_key,),
            ).fetchone()
            if not row:
                return {
                    "owner_key": self.owner_key,
                    "revision": 0,
                    "rendered_fact_ids_json": "[]",
                    "render_dirty": 0,
                    "git_dirty": 0,
                }
            return dict(row)

    def save_render_state(
        self,
        *,
        revision: int,
        file_hash: str | None,
        file_mtime: float | None,
        rendered_fact_ids: list[str],
        valid_snapshot_body: str | None,
        render_dirty: bool = False,
        git_dirty: bool = False,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_render_state (
                    owner_key, revision, file_hash, file_mtime, rendered_fact_ids_json,
                    valid_snapshot_body, render_dirty, git_dirty
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_key) DO UPDATE SET
                    revision = excluded.revision,
                    file_hash = excluded.file_hash,
                    file_mtime = excluded.file_mtime,
                    rendered_fact_ids_json = excluded.rendered_fact_ids_json,
                    valid_snapshot_body = excluded.valid_snapshot_body,
                    render_dirty = excluded.render_dirty,
                    git_dirty = excluded.git_dirty
                """,
                (
                    self.owner_key,
                    revision,
                    file_hash,
                    file_mtime,
                    json.dumps(rendered_fact_ids, ensure_ascii=False),
                    valid_snapshot_body,
                    1 if render_dirty else 0,
                    1 if git_dirty else 0,
                ),
            )
            conn.commit()

    def search_confirmed(self, query: str, *, limit: int = 10) -> list[dict]:
        q = (query or "").strip().lower()
        facts = self.list_confirmed()
        if not q:
            return facts[:limit]
        matched = [f for f in facts if q in f["statement"].lower() or q in f["slot_key"].lower()]
        return matched[:limit]
