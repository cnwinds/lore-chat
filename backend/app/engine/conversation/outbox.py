from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path

MAX_OUTBOX_ATTEMPTS = 5


def _now() -> str:
    from app.time import now_iso_seconds

    return now_iso_seconds()


def _future(seconds: float) -> str:
    from datetime import timedelta

    from app.time import now_display

    return (now_display() + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def default_deletion_ledger_path(conversations_dir: Path) -> Path:
    return conversations_dir.parent / "migrations" / "conversation-deletions.jsonl"


def append_deletion_ledger(
    path: Path, cid: str, deletion_id: str, deleted_at: str, options: dict
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "conversation_id": cid,
        "deletion_id": deletion_id,
        "deleted_at": deleted_at,
        "options": options,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


# session_observe：归档/显式即时入队标记（消费时跳过空闲校验）
SESSION_OBSERVE_IMMEDIATE = "immediate"


class DerivationOutbox:
    """会话派生任务队列（index_fts / index_vector / session_observe_memory）。"""

    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock):
        self.conn = conn
        self._lock = lock

    def enqueue_index_jobs(self, message_id: str, turn_id: str | None) -> None:
        now = _now()
        for kind in ("index_fts", "index_vector"):
            self.conn.execute(
                """
                INSERT INTO derivation_outbox(
                    kind, source_message_id, source_revision, turn_id,
                    status, attempts, next_run_at, created_at, updated_at
                ) VALUES (?, ?, 1, ?, 'pending', 0, ?, ?, ?)
                """,
                (kind, message_id, turn_id, now, now, now),
            )

    def enqueue_observe_memory(self, message_id: str, turn_id: str) -> None:
        """已废弃：按条观察不再入队；保留方法以免旧调用崩溃。"""
        return

    def cancel_session_observe(self, conversation_id: str) -> int:
        """取消该会话未完成的 session_observe（续聊后须重新空闲再抽）。"""
        now = _now()
        source = f"conv:{conversation_id}"
        cur = self.conn.execute(
            """
            UPDATE derivation_outbox
            SET status = 'cancelled', updated_at = ?
            WHERE kind = 'session_observe_memory'
              AND source_message_id = ?
              AND status IN ('pending', 'blocked')
            """,
            (now, source),
        )
        return int(cur.rowcount or 0)

    def enqueue_session_observe(
        self, conversation_id: str, *, immediate: bool = False
    ) -> bool:
        """为会话入队 session_observe_memory。

        immediate=True：归档/显式路径，turn_id=SESSION_OBSERVE_IMMEDIATE，消费时不校验空闲。
        已有未完成任务：immediate 可升级标记；否则跳过。
        """
        now = _now()
        source = f"conv:{conversation_id}"
        existing = self.conn.execute(
            """
            SELECT id, turn_id, status FROM derivation_outbox
            WHERE kind = 'session_observe_memory'
              AND source_message_id = ?
              AND status IN ('pending', 'running', 'blocked')
            LIMIT 1
            """,
            (source,),
        ).fetchone()
        if existing:
            if immediate and existing["status"] in ("pending", "blocked"):
                self.conn.execute(
                    """
                    UPDATE derivation_outbox
                    SET turn_id = ?, next_run_at = ?, updated_at = ?,
                        status = 'pending'
                    WHERE id = ?
                    """,
                    (SESSION_OBSERVE_IMMEDIATE, now, now, existing["id"]),
                )
                return True
            if immediate and existing["status"] == "running":
                # 本轮结束后由 memory_immediate_pending 再入队；先升级以免失败重试撞 idle 门闩
                self.conn.execute(
                    """
                    UPDATE derivation_outbox
                    SET turn_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (SESSION_OBSERVE_IMMEDIATE, now, existing["id"]),
                )
                return False
            return False
        turn_id = SESSION_OBSERVE_IMMEDIATE if immediate else None
        # 不可写死 revision=1：done 行仍占唯一键，二次入队会 IntegrityError
        rev_row = self.conn.execute(
            """
            SELECT COALESCE(MAX(source_revision), 0) AS m
            FROM derivation_outbox
            WHERE kind = 'session_observe_memory' AND source_message_id = ?
            """,
            (source,),
        ).fetchone()
        next_rev = int(rev_row["m"] or 0) + 1
        self.conn.execute(
            """
            INSERT INTO derivation_outbox(
                kind, source_message_id, source_revision, turn_id,
                status, attempts, next_run_at, created_at, updated_at
            ) VALUES ('session_observe_memory', ?, ?, ?, 'pending', 0, ?, ?, ?)
            """,
            (source, next_rev, turn_id, now, now, now),
        )
        return True

    def cancel_legacy_observe_memory(self) -> int:
        """取消未完成的按条 observe_memory（已废除，升级时清理）。"""
        now = _now()
        cur = self.conn.execute(
            """
            UPDATE derivation_outbox
            SET status = 'cancelled', updated_at = ?
            WHERE kind = 'observe_memory'
              AND status IN ('pending', 'blocked', 'running')
            """,
            (now,),
        )
        return int(cur.rowcount or 0)

    def activate_observe_jobs(self, turn_id: str, *, observation_allowed: bool) -> None:
        status = "pending" if observation_allowed else "cancelled"
        now = _now()
        self.conn.execute(
            """
            UPDATE derivation_outbox
            SET status = ?, updated_at = ?, next_run_at = ?
            WHERE turn_id = ? AND kind = 'observe_memory' AND status = 'blocked'
            """,
            (status, now, now, turn_id),
        )

    def claim(self, kind: str, limit: int = 10, lease_seconds: int = 60) -> list[dict]:
        with self._lock:
            now = _now()
            if kind == "observe_memory":
                # 按条观察已废除：不再 claim
                rows = []
            elif kind == "session_observe_memory":
                rows = self.conn.execute(
                    """
                    SELECT * FROM derivation_outbox
                    WHERE kind = 'session_observe_memory'
                      AND (
                            status = 'pending'
                            OR (status = 'running' AND (
                                locked_until IS NULL OR locked_until <= ?
                            ))
                      )
                      AND (next_run_at IS NULL OR next_run_at <= ?)
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (now, now, limit),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    """
                    SELECT * FROM derivation_outbox
                    WHERE kind = ?
                      AND (
                            status = 'pending'
                            OR (status = 'running' AND (
                                locked_until IS NULL OR locked_until <= ?
                            ))
                      )
                      AND (next_run_at IS NULL OR next_run_at <= ?)
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (kind, now, now, limit),
                ).fetchall()
            if not rows:
                return []
            locked_until = _future(lease_seconds)
            jobs: list[dict] = []
            for row in rows:
                self.conn.execute(
                    """
                    UPDATE derivation_outbox
                    SET status = 'running', locked_until = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (locked_until, now, row["id"]),
                )
                job = dict(row)
                job["status"] = "running"
                job["locked_until"] = locked_until
                jobs.append(job)
            self.conn.commit()
            return jobs

    def cancel_pending_for_conversation(self, cid: str, updated_at: str) -> None:
        """在 ConversationStore 已持有 lock 的同一事务内调用；不在此 commit。"""
        session_source = f"conv:{cid}"
        self.conn.execute(
            """
            UPDATE derivation_outbox
            SET status = 'cancelled', updated_at = ?
            WHERE status IN ('pending', 'running', 'blocked')
              AND (
                    turn_id IN (SELECT id FROM turns WHERE conversation_id = ?)
                    OR source_message_id IN (
                        SELECT id FROM messages WHERE conversation_id = ?
                    )
                    OR source_message_id = ?
              )
            """,
            (updated_at, cid, cid, session_source),
        )

    def complete(self, job_id: int) -> None:
        with self._lock:
            self.conn.execute(
                """
                UPDATE derivation_outbox
                SET status = 'done', locked_until = NULL, updated_at = ?
                WHERE id = ?
                """,
                (_now(), job_id),
            )
            self.conn.commit()

    def fail(self, job_id: int, error: str, backoff: float = 1.0) -> None:
        with self._lock:
            row = self.conn.execute(
                "SELECT attempts, status FROM derivation_outbox WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return
            # 会话已删除等路径可能先 cancelled；勿把终态任务救回 pending
            if row["status"] not in ("running", "pending", "blocked"):
                return
            attempts = int(row["attempts"]) + 1
            if attempts >= MAX_OUTBOX_ATTEMPTS:
                status = "dead"
                next_run_at = None
            else:
                status = "pending"
                next_run_at = _future(backoff * (2 ** (attempts - 1)))
            self.conn.execute(
                """
                UPDATE derivation_outbox
                SET attempts = ?, status = ?, next_run_at = ?, last_error = ?,
                    locked_until = NULL, updated_at = ?
                WHERE id = ? AND status IN ('running', 'pending', 'blocked')
                """,
                (attempts, status, next_run_at, error, _now(), job_id),
            )
            self.conn.commit()

    def list_jobs(
        self,
        *,
        kind: str | None = None,
        message_id: str | None = None,
    ) -> list[dict]:
        with self._lock:
            clauses = ["1=1"]
            params: list = []
            if kind:
                clauses.append("kind = ?")
                params.append(kind)
            if message_id:
                clauses.append("source_message_id = ?")
                params.append(message_id)
            rows = self.conn.execute(
                f"SELECT * FROM derivation_outbox WHERE {' AND '.join(clauses)} ORDER BY id",
                params,
            ).fetchall()
            return [dict(r) for r in rows]
