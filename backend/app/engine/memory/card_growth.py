from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_GROWTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS card_growth_log (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  kind TEXT NOT NULL,
  conversation_id TEXT,
  items_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_card_growth_scope
  ON card_growth_log(scope, created_at DESC);

CREATE TABLE IF NOT EXISTS card_scope_state (
  scope TEXT PRIMARY KEY,
  last_consolidated_at TEXT,
  last_faded_at TEXT
);
"""


class CardGrowthLog:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_GROWTH_SCHEMA)
            self._migrate_last_evolved(conn)

    @staticmethod
    def _migrate_last_evolved(conn: sqlite3.Connection) -> None:
        cursor = conn.execute("PRAGMA table_info(card_scope_state)")
        columns = {row[1] for row in cursor.fetchall()}
        if "last_evolved_at" not in columns:
            conn.execute(
                "ALTER TABLE card_scope_state ADD COLUMN last_evolved_at TEXT"
            )
            conn.commit()

    def append(
        self,
        scope: str,
        kind: str,
        items: list[dict],
        *,
        conversation_id: str | None = None,
    ) -> str | None:
        if not items:
            return None
        entry_id = str(uuid.uuid4())
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO card_growth_log (
                    id, scope, kind, conversation_id, items_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    scope,
                    kind,
                    conversation_id,
                    json.dumps(items, ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()
        return entry_id

    def list(self, scope: str, *, limit: int = 50) -> list[dict]:
        lim = max(1, int(limit))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, kind, created_at, conversation_id, items_json
                FROM card_growth_log
                WHERE scope = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (scope, lim),
            ).fetchall()
        out: list[dict] = []
        for row in rows:
            out.append(
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "created_at": row["created_at"],
                    "conversation_id": row["conversation_id"],
                    "items": json.loads(row["items_json"] or "[]"),
                }
            )
        return out

    def scope_state(self, scope: str) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT last_consolidated_at, last_faded_at, last_evolved_at
                FROM card_scope_state WHERE scope = ?
                """,
                (scope,),
            ).fetchone()
        if not row:
            return {
                "last_consolidated_at": None,
                "last_faded_at": None,
                "last_evolved_at": None,
            }
        try:
            last_evolved = row["last_evolved_at"]
        except (KeyError, IndexError):
            last_evolved = None
        return {
            "last_consolidated_at": row["last_consolidated_at"],
            "last_faded_at": row["last_faded_at"],
            "last_evolved_at": last_evolved,
        }

    def mark_evolved(self, scope: str, ts: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO card_scope_state (
                    scope, last_consolidated_at, last_faded_at, last_evolved_at
                ) VALUES (?, NULL, NULL, ?)
                ON CONFLICT(scope) DO UPDATE SET last_evolved_at = excluded.last_evolved_at
                """,
                (scope, ts),
            )
            conn.commit()

    def mark_consolidated(self, scope: str, ts: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO card_scope_state (scope, last_consolidated_at, last_faded_at)
                VALUES (?, ?, NULL)
                ON CONFLICT(scope) DO UPDATE SET last_consolidated_at = excluded.last_consolidated_at
                """,
                (scope, ts),
            )
            conn.commit()

    def mark_faded(self, scope: str, ts: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO card_scope_state (scope, last_consolidated_at, last_faded_at)
                VALUES (?, NULL, ?)
                ON CONFLICT(scope) DO UPDATE SET last_faded_at = excluded.last_faded_at
                """,
                (scope, ts),
            )
            conn.commit()

    def purge(self, scope: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM card_growth_log WHERE scope = ?", (scope,)
            )
            n = cur.rowcount
            conn.execute("DELETE FROM card_scope_state WHERE scope = ?", (scope,))
            conn.commit()
            return n
