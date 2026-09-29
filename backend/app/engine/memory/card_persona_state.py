"""角色知识卡与人设进化相关的 per-scope 状态。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS card_persona_marks (
  scope TEXT NOT NULL,
  card_id TEXT NOT NULL,
  state TEXT NOT NULL,
  statement_hash TEXT NOT NULL,
  revision_id TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (scope, card_id)
);

CREATE TABLE IF NOT EXISTS card_proposals (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  target TEXT NOT NULL,
  title TEXT NOT NULL,
  reason TEXT NOT NULL,
  basis_json TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_card_proposals_scope
  ON card_proposals(scope, created_at DESC);
"""


class CardPersonaState:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def marks(self, scope: str) -> dict[str, dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT card_id, state, statement_hash, revision_id, updated_at
                FROM card_persona_marks WHERE scope = ?
                """,
                (scope,),
            ).fetchall()
        return {
            row["card_id"]: {
                "card_id": row["card_id"],
                "state": row["state"],
                "statement_hash": row["statement_hash"],
                "revision_id": row["revision_id"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        }

    def set_marks(
        self,
        scope: str,
        items: list[tuple[str, str, str, str | None]],
    ) -> None:
        if not items:
            return
        stamp = _now()
        with self._connect() as conn:
            for card_id, state, statement_hash, revision_id in items:
                conn.execute(
                    """
                    INSERT INTO card_persona_marks(
                        scope, card_id, state, statement_hash, revision_id, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(scope, card_id) DO UPDATE SET
                        state = excluded.state,
                        statement_hash = excluded.statement_hash,
                        revision_id = excluded.revision_id,
                        updated_at = excluded.updated_at
                    """,
                    (scope, card_id, state, statement_hash, revision_id, stamp),
                )
            conn.commit()

    def reject_revision(self, scope: str, revision_id: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE card_persona_marks
                SET state = 'rejected', updated_at = ?
                WHERE scope = ? AND revision_id = ? AND state = 'merged'
                """,
                (_now(), scope, revision_id),
            )
            conn.commit()
            return int(cur.rowcount)

    def add_proposal(
        self,
        scope: str,
        *,
        target: str,
        title: str,
        reason: str,
        basis: list[dict],
    ) -> dict:
        pid = uuid.uuid4().hex[:12]
        stamp = _now()
        row = {
            "id": pid,
            "scope": scope,
            "target": target,
            "title": title,
            "reason": reason,
            "basis": basis,
            "status": "pending",
            "created_at": stamp,
            "decided_at": None,
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO card_proposals(
                    id, scope, target, title, reason, basis_json, status, created_at, decided_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, NULL)
                """,
                (
                    pid,
                    scope,
                    target,
                    title,
                    reason,
                    json.dumps(basis, ensure_ascii=False),
                    stamp,
                ),
            )
            conn.commit()
        return row

    def list_proposals(self, scope: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM card_proposals
                WHERE scope = ?
                ORDER BY created_at DESC
                """,
                (scope,),
            ).fetchall()
        return [self._proposal_row(r) for r in rows]

    def get_proposal(self, scope: str, proposal_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM card_proposals WHERE scope = ? AND id = ?",
                (scope, proposal_id),
            ).fetchone()
        if row is None:
            return None
        return self._proposal_row(row)

    def decide_proposal(
        self, scope: str, proposal_id: str, status: str
    ) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM card_proposals WHERE scope = ? AND id = ?",
                (scope, proposal_id),
            ).fetchone()
            if row is None or row["status"] != "pending":
                return None
            stamp = _now()
            conn.execute(
                """
                UPDATE card_proposals
                SET status = ?, decided_at = ?
                WHERE scope = ? AND id = ?
                """,
                (status, stamp, scope, proposal_id),
            )
            conn.commit()
            return self.get_proposal(scope, proposal_id)

    def purge(self, scope: str) -> int:
        with self._connect() as conn:
            cur1 = conn.execute(
                "DELETE FROM card_persona_marks WHERE scope = ?", (scope,)
            )
            cur2 = conn.execute(
                "DELETE FROM card_proposals WHERE scope = ?", (scope,)
            )
            conn.commit()
            return int(cur1.rowcount) + int(cur2.rowcount)

    @staticmethod
    def _proposal_row(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "scope": row["scope"],
            "target": row["target"],
            "title": row["title"],
            "reason": row["reason"],
            "basis": json.loads(row["basis_json"] or "[]"),
            "status": row["status"],
            "created_at": row["created_at"],
            "decided_at": row["decided_at"],
        }
