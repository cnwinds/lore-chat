from __future__ import annotations

import json
from collections.abc import Iterable
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.engine.conversation.outbox import (
    DerivationOutbox,
    append_deletion_ledger,
    default_deletion_ledger_path,
)
from app.engine.conversation.shared import (
    TurnInProgress,
    dumps_json as _dumps,
    loads_json as _loads,
    new_id as _new_id,
    now_iso as _now,
    title_from_text as _title_from_text,
)
from app.engine.conversation.turn_lifecycle import TurnLifecycle


class _ConversationFTSLike(Protocol):
    def delete_conversation(self, conversation_id: str) -> None: ...


class _ConversationVectorLike(Protocol):
    def delete_conversation(self, conversation_id: str) -> None: ...


class _IndexRevisionLike(Protocol):
    def bump(self) -> int: ...


class _IndexerLike(Protocol):
    def remove_conversation(self, cid: str) -> None: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    active_turn_id TEXT,
    indexed_dirty INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    ts TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'complete',
    client_message_id TEXT,
    in_reply_to_message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
    timeline_json TEXT,
    sources_json TEXT,
    total_duration_ms INTEGER,
    doc_context_json TEXT,
    attachments_json TEXT,
    primary_doc TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_seq
    ON messages(conversation_id, seq);
CREATE UNIQUE INDEX IF NOT EXISTS ux_messages_in_reply_to
    ON messages(in_reply_to_message_id)
    WHERE in_reply_to_message_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    client_message_id TEXT NOT NULL,
    user_message_id TEXT NOT NULL,
    assistant_message_id TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    observation_allowed INTEGER NOT NULL DEFAULT 0,
    locked_by TEXT,
    locked_until TEXT,
    started_at TEXT NOT NULL,
    finalized_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_turns_conversation_client_msg
    ON turns(conversation_id, client_message_id);

CREATE TABLE IF NOT EXISTS conversation_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    doc_path TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    covered_through_message_id TEXT,
    status TEXT NOT NULL DEFAULT 'current',
    is_primary INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversation_summaries_cid
    ON conversation_summaries(conversation_id);

CREATE TABLE IF NOT EXISTS derivation_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    source_message_id TEXT NOT NULL,
    source_revision INTEGER NOT NULL DEFAULT 1,
    turn_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_run_at TEXT,
    locked_by TEXT,
    locked_until TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_derivation_outbox_status
    ON derivation_outbox(kind, status);

CREATE UNIQUE INDEX IF NOT EXISTS ux_derivation_outbox_kind_msg_rev
    ON derivation_outbox(kind, source_message_id, source_revision);

CREATE TABLE IF NOT EXISTS conversation_system_events (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversation_system_events_cid
    ON conversation_system_events(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS conversation_deletion_ledger (
    conversation_id TEXT NOT NULL,
    deletion_id TEXT NOT NULL,
    deleted_at TEXT NOT NULL,
    options_json TEXT
);

CREATE TABLE IF NOT EXISTS migration_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class ConversationStore:
    """会话规范存储：SQLite（`conversations.db`），消息级持久化 + turn 状态机。"""

    def __init__(self, path: str | Path):
        raw = Path(path)
        if raw.suffix == ".json":
            self.dir = raw.parent / "conversations"
            legacy_single = raw
        else:
            self.dir = raw
            legacy_single = self.dir.parent / "conversations.json"
        self.dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.dir / "conversations.db"
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.executescript(_SCHEMA)
            self._ensure_memory_schedule_columns()
            self.conn.commit()

        if legacy_single.exists():
            self._migrate_legacy_single_file(legacy_single)

        if (self.dir / "index.json").exists() and not self._json_shards_migrated():
            from .conversation_migrate import migrate_json_shards

            migrate_json_shards(self.dir)

        self._outbox = DerivationOutbox(self.conn, self._lock)
        self._turn_lifecycle = TurnLifecycle(self)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _ensure_memory_schedule_columns(self) -> None:
        cols = {
            r[1]
            for r in self.conn.execute("PRAGMA table_info(conversations)").fetchall()
        }
        alters = []
        if "memory_dirty" not in cols:
            alters.append(
                "ALTER TABLE conversations ADD COLUMN memory_dirty INTEGER NOT NULL DEFAULT 0"
            )
        if "last_user_message_at" not in cols:
            alters.append("ALTER TABLE conversations ADD COLUMN last_user_message_at TEXT")
        if "last_memory_extract_at" not in cols:
            alters.append(
                "ALTER TABLE conversations ADD COLUMN last_memory_extract_at TEXT"
            )
        if "memory_extract_revision" not in cols:
            alters.append(
                "ALTER TABLE conversations ADD COLUMN memory_extract_revision "
                "INTEGER NOT NULL DEFAULT 0"
            )
        if "memory_immediate_pending" not in cols:
            alters.append(
                "ALTER TABLE conversations ADD COLUMN memory_immediate_pending "
                "INTEGER NOT NULL DEFAULT 0"
            )
        for sql in alters:
            self.conn.execute(sql)

    def _json_shards_migrated(self) -> bool:
        row = self.conn.execute(
            "SELECT value FROM migration_meta WHERE key = 'json_shards_v1'"
        ).fetchone()
        return row is not None

    @staticmethod
    def _bump_cas_timestamp(prev: str) -> str:
        """保证 CAS 键相对 prev 严格前进（秒级时钟同秒续聊/归档时必需）。"""
        try:
            dt = datetime.fromisoformat(prev)
        except ValueError:
            return f"{prev}+1"
        from datetime import timedelta

        return (dt + timedelta(microseconds=1)).isoformat(timespec="microseconds")

    @classmethod
    def _ensure_cas_advances(cls, prev: str, ts: str) -> str:
        """新 dirty 时间戳必须 > prev，防止写回更旧秒级时间导致 CAS 误清。"""
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

    def _mark_memory_dirty_unlocked(self, cid: str, *, at: str | None = None) -> None:
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
        # 续聊：取消已排队的空闲抽取，须再次空闲后重抽（规格 §6.2）
        self._outbox.cancel_session_observe(cid)

    def mark_memory_dirty(self, cid: str, *, at: str | None = None) -> None:
        with self._lock:
            self._mark_memory_dirty_unlocked(cid, at=at)
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

    def clear_memory_dirty(
        self,
        cid: str,
        *,
        at: str | None = None,
        expected_last_user_message_at: str | None = None,
    ) -> int | None:
        """成功抽取后清 dirty，并递增 memory_extract_revision。

        若传入 ``expected_last_user_message_at``，则 CAS：仅当该时间戳未变才清 dirty
        （防止 running 任务结束时抹掉续聊后的 dirty，规格 §6.2）。
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

    def get_memory_extract_revision(self, cid: str) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT memory_extract_revision FROM conversations WHERE id = ?",
                (cid,),
            ).fetchone()
            if not row:
                return 0
            return int(row["memory_extract_revision"] or 0)

    def _enqueue_session_observe_unlocked(
        self, conversation_id: str, *, immediate: bool = False
    ) -> bool:
        return self._outbox.enqueue_session_observe(
            conversation_id, immediate=immediate
        )

    def enqueue_session_observe(
        self, conversation_id: str, *, immediate: bool = False
    ) -> bool:
        with self._lock:
            ok = self._enqueue_session_observe_unlocked(
                conversation_id, immediate=immediate
            )
            self.conn.commit()
            return ok

    def batch_mark_dirty_and_enqueue_session_observe(
        self,
        conversation_ids: list[str],
        *,
        mark_dirty: bool = True,
        immediate: bool = False,
    ) -> int:
        """批量标 dirty 并入队 session_observe（供 backfill，不暴露 lock）。"""
        with self._lock:
            n = 0
            for cid in conversation_ids:
                if mark_dirty:
                    self._mark_memory_dirty_unlocked(cid)
                if self._enqueue_session_observe_unlocked(cid, immediate=immediate):
                    n += 1
            self.conn.commit()
            return n

    def list_conversation_ids(self) -> list[str]:
        with self._lock:
            rows = self.conn.execute("SELECT id FROM conversations").fetchall()
            return [r["id"] for r in rows]

    def cancel_legacy_observe_memory(self) -> int:
        """取消未完成的按条 observe_memory（供 MemoryWorker 经 store API 调用）。"""
        with self._lock:
            n = self._outbox.cancel_legacy_observe_memory()
            self.conn.commit()
            return n

    def is_memory_extract_idle(self, cid: str, *, idle_hours: float = 24.0) -> bool:
        """是否满足「最后用户消息后已空闲」——消费时再核一次。"""
        from datetime import datetime, timedelta, timezone

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

    def _request_immediate_memory_extract_unlocked(
        self, cid: str, *, at: str | None = None
    ) -> bool:
        self._mark_memory_dirty_unlocked(cid, at=at)
        ok = self._enqueue_session_observe_unlocked(cid, immediate=True)
        if not ok:
            # 已有 running：升级其 turn_id 后仍须在本轮结束后再抽（规格：归档即时）
            self.conn.execute(
                """
                UPDATE conversations
                SET memory_immediate_pending = 1, updated_at = ?
                WHERE id = ?
                """,
                (at or _now(), cid),
            )
        return ok

    def request_immediate_memory_extract(self, cid: str) -> bool:
        """归档/显式路径：标 dirty 并立刻入队（不等空闲）。"""
        with self._lock:
            ok = self._request_immediate_memory_extract_unlocked(cid)
            self.conn.commit()
            return ok

    def consume_memory_immediate_pending_if_dirty(self, cid: str) -> bool:
        """清除归档即时待办；若曾挂起则返回 True（应再入队 immediate）。

        不要求仍 dirty：同秒归档时 CAS 可能已清 dirty，但即时重抽仍须执行。
        """
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

    def list_idle_dirty_conversations(
        self, *, idle_hours: float = 24.0, limit: int = 20
    ) -> list[dict]:
        """最后用户消息已空闲 idle_hours 且仍 dirty 的会话。"""
        from datetime import datetime, timedelta, timezone

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

    def list_user_messages_text(self, cid: str) -> list[str]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT text FROM messages
                WHERE conversation_id = ? AND role = 'user'
                ORDER BY seq ASC
                """,
                (cid,),
            ).fetchall()
            return [(r["text"] or "") for r in rows]

    def list_dialogue_turns(self, cid: str) -> list[tuple[str, str]]:
        """按序返回 (role, text)，仅 user/assistant，供会话级记忆抽取消歧。"""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT role, text FROM messages
                WHERE conversation_id = ? AND role IN ('user', 'assistant')
                ORDER BY seq ASC
                """,
                (cid,),
            ).fetchall()
            out: list[tuple[str, str]] = []
            for r in rows:
                text = (r["text"] or "").strip()
                if text:
                    out.append((r["role"], text))
            return out

    def _next_seq(self, cid: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM messages WHERE conversation_id = ?",
            (cid,),
        ).fetchone()
        return int(row["n"])

    def _enqueue_index_jobs(self, message_id: str, turn_id: str | None) -> None:
        self._outbox.enqueue_index_jobs(message_id, turn_id)

    def _enqueue_observe_memory(self, message_id: str, turn_id: str) -> None:
        self._outbox.enqueue_observe_memory(message_id, turn_id)

    def _activate_observe_jobs(self, turn_id: str, *, observation_allowed: bool) -> None:
        self._outbox.activate_observe_jobs(turn_id, observation_allowed=observation_allowed)

    @staticmethod
    def _message_row_to_dict(row: sqlite3.Row) -> dict:
        msg: dict = {
            "id": row["id"],
            "role": row["role"],
            "text": row["text"] or "",
            "ts": row["ts"],
            "status": row["status"],
        }
        if row["client_message_id"]:
            msg["client_message_id"] = row["client_message_id"]
        if row["in_reply_to_message_id"]:
            msg["in_reply_to_message_id"] = row["in_reply_to_message_id"]
        if row["timeline_json"] is not None:
            msg["timeline"] = _loads(row["timeline_json"], [])
        if row["sources_json"] is not None:
            msg["sources"] = _loads(row["sources_json"], [])
        if row["total_duration_ms"] is not None:
            msg["total_duration_ms"] = row["total_duration_ms"]
        if row["doc_context_json"] is not None:
            from app.engine.doc_context import normalize_doc_context_items

            msg["doc_context"] = normalize_doc_context_items(
                _loads(row["doc_context_json"], [])
            )
        if row["attachments_json"] is not None:
            msg["attachments"] = _loads(row["attachments_json"], [])
        if row["primary_doc"]:
            msg["primary_doc"] = row["primary_doc"]
        return msg

    def _load_messages(self, cid: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY seq ASC",
            (cid,),
        ).fetchall()
        return [self._message_row_to_dict(r) for r in rows]

    def get_message_window(
        self,
        cid: str,
        message_id: str,
        *,
        before_messages: int = 0,
        after_messages: int = 0,
    ) -> list[dict]:
        with self._lock:
            self._conversation_row(cid)
            anchor = self.conn.execute(
                "SELECT seq FROM messages WHERE id = ? AND conversation_id = ?",
                (message_id, cid),
            ).fetchone()
            if anchor is None:
                raise KeyError(message_id)
            seq = int(anchor["seq"])
            rows = self.conn.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ?
                  AND seq BETWEEN ? AND ?
                  AND role IN ('user', 'assistant')
                ORDER BY seq ASC
                """,
                (cid, seq - before_messages, seq + after_messages),
            ).fetchall()
        return [self._message_row_to_dict(r) for r in rows]

    def _summary_state(self, cid: str) -> tuple[bool, str | None, str | None]:
        row = self.conn.execute(
            """
            SELECT doc_path, created_at FROM conversation_summaries
            WHERE conversation_id = ? AND status = 'current' AND is_primary = 1
            ORDER BY revision DESC LIMIT 1
            """,
            (cid,),
        ).fetchone()
        if row is None:
            return False, None, None
        return True, row["doc_path"], row["created_at"]

    def _conversation_row(self, cid: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (cid,)
        ).fetchone()
        if row is None:
            raise KeyError(cid)
        return row

    def _conv_to_dict(self, row: sqlite3.Row) -> dict:
        cid = row["id"]
        summarized, summary_path, summarized_at = self._summary_state(cid)
        summaries = self._list_summaries_unlocked(cid)
        active_turn_id = row["active_turn_id"]
        active_turn = None
        if active_turn_id:
            trow = self.conn.execute(
                "SELECT id, status, started_at FROM turns WHERE id = ?",
                (active_turn_id,),
            ).fetchone()
            if trow is not None:
                active_turn = {
                    "turn_id": trow["id"],
                    "status": trow["status"],
                    "started_at": trow["started_at"],
                }
        return {
            "id": cid,
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "active_turn_id": active_turn_id,
            "active_turn": active_turn,
            "messages": self._load_messages(cid),
            "summaries": summaries,
            "summarized": summarized,
            "summary_path": summary_path,
            "summarized_at": summarized_at,
            "indexed_dirty": bool(row["indexed_dirty"]),
        }

    def _mark_dirty_and_stale(self, cid: str) -> None:
        self.conn.execute(
            "UPDATE conversations SET indexed_dirty = 1 WHERE id = ?", (cid,)
        )
        self.conn.execute(
            """
            UPDATE conversation_summaries SET status = 'stale'
            WHERE conversation_id = ? AND status = 'current'
            """,
            (cid,),
        )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, title: str | None = None) -> str:
        cid = uuid.uuid4().hex[:12]
        stamp = _now()
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO conversations(id, title, created_at, updated_at, active_turn_id, indexed_dirty)
                VALUES (?, ?, ?, ?, NULL, 0)
                """,
                (cid, title or "新对话", stamp, stamp),
            )
            self.conn.commit()
        return cid

    def get(self, cid: str) -> dict:
        with self._lock:
            row = self._conversation_row(cid)
            return self._conv_to_dict(row)

    def list_all(self) -> list[dict]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM conversations").fetchall()
            items = []
            for row in rows:
                cid = row["id"]
                count = self.conn.execute(
                    "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?",
                    (cid,),
                ).fetchone()["n"]
                summarized, summary_path, _ = self._summary_state(cid)
                items.append(
                    {
                        "id": cid,
                        "title": row["title"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "message_count": int(count),
                        "summarized": summarized,
                        "summary_path": summary_path,
                    }
                )
        return sorted(items, key=lambda c: c["updated_at"], reverse=True)

    def _default_deletion_ledger_path(self) -> Path:
        return default_deletion_ledger_path(self.dir)

    def delete(
        self,
        cid: str,
        *,
        conversation_fts: "_ConversationFTSLike | None" = None,
        conversation_vector: "_ConversationVectorLike | None" = None,
        indexer: "_IndexerLike | None" = None,
        index_revision: "_IndexRevisionLike | None" = None,
        ledger_path: str | Path | None = None,
        delete_summary: bool = True,
    ) -> None:
        """删除会话事务顺序（spec §16）：

        0. 先校验会话存在，缺失的 cid 直接抛出 KeyError，不写入任何凭据——
           避免为不存在的会话产生幽灵 ledger 记录。
        1. 存在性确认后，追加并 fsync 删除凭据（跨版本 JSONL ledger）——即使后续
           步骤崩溃，回填/审计也能从 ledger 得知该会话已被判定删除。
        2. 在同一 SQLite 事务内取消该会话尚未完成的 outbox 派生任务。
        3. 删除消息/turns/摘要关系/会话行本身。
        4. 通知 `ConversationFTS` 清理消息级 FTS（`conversation_chunks_v2`）。
        5. 通知 `ConversationVector` 清理消息级向量索引。
        6. 通知旧版文档级 `Indexer` 清理遗留的 `conv:{cid}` FTS 记录。
        """
        with self._lock:
            self._conversation_row(cid)

        deletion_id = _new_id()
        deleted_at = _now()
        options = {"delete_summary": delete_summary}
        ledger_file = Path(ledger_path) if ledger_path else self._default_deletion_ledger_path()
        append_deletion_ledger(ledger_file, cid, deletion_id, deleted_at, options)

        with self._lock:
            self._conversation_row(cid)
            self.conn.execute(
                """
                INSERT INTO conversation_deletion_ledger(
                    conversation_id, deletion_id, deleted_at, options_json
                ) VALUES (?, ?, ?, ?)
                """,
                (cid, deletion_id, deleted_at, _dumps(options)),
            )
            self._outbox.cancel_pending_for_conversation(cid, deleted_at)
            self.conn.execute("DELETE FROM turns WHERE conversation_id = ?", (cid,))
            if delete_summary:
                self.conn.execute(
                    "DELETE FROM conversation_summaries WHERE conversation_id = ?", (cid,)
                )
            self.conn.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
            self.conn.execute("DELETE FROM conversations WHERE id = ?", (cid,))
            self.conn.commit()

        index_cleared = False
        if conversation_fts is not None:
            conversation_fts.delete_conversation(cid)
            index_cleared = True
        if conversation_vector is not None:
            try:
                conversation_vector.delete_conversation(cid)
            except Exception:
                from app.logging_config import get_logger

                get_logger("conversations").warning(
                    "会话向量索引清理失败 conversation_id=%s", cid, exc_info=True
                )
            index_cleared = True
        if index_revision is not None and index_cleared:
            index_revision.bump()
        if indexer is not None:
            indexer.remove_conversation(cid)

    # ------------------------------------------------------------------
    # Turn-based 持久化
    # ------------------------------------------------------------------

    def begin_turn(
        self,
        cid: str,
        user_text: str,
        client_message_id: str,
        observation_allowed: bool = False,
        *,
        user_ts: str | None = None,
        doc_context: list[str] | None = None,
        primary_doc: str | None = None,
        attachments: list[str] | None = None,
    ) -> dict:
        return self._turn_lifecycle.begin_turn(
            cid,
            user_text,
            client_message_id,
            observation_allowed,
            user_ts=user_ts,
            doc_context=doc_context,
            primary_doc=primary_doc,
            attachments=attachments,
        )

    def finalize_turn(self, cid: str, turn_id: str, assistant: dict) -> dict | None:
        return self._turn_lifecycle.finalize_turn(cid, turn_id, assistant)

    def list_running_turns(self) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT id AS turn_id, conversation_id, client_message_id, started_at
                FROM turns WHERE status = 'running'
                """
            ).fetchall()
            return [
                {
                    "turn_id": r["turn_id"],
                    "conversation_id": r["conversation_id"],
                    "client_message_id": r["client_message_id"],
                    "started_at": r["started_at"],
                }
                for r in rows
            ]

    def get_turn(self, turn_id: str) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM turns WHERE id = ?", (turn_id,)
            ).fetchone()
            if row is None:
                return None
            return {
                "turn_id": row["id"],
                "conversation_id": row["conversation_id"],
                "status": row["status"],
                "client_message_id": row["client_message_id"],
                "started_at": row["started_at"],
                "finalized_at": row["finalized_at"],
            }

    def append_exchange(
        self,
        cid: str,
        user_text: str,
        assistant_msg: dict,
        user_ts: str | None = None,
        *,
        doc_context: list[str] | None = None,
        primary_doc: str | None = None,
        attachments: list[str] | None = None,
    ) -> dict:
        client_message_id = _new_id()
        turn = self.begin_turn(
            cid,
            user_text,
            client_message_id,
            observation_allowed=False,
            user_ts=user_ts,
            doc_context=doc_context,
            primary_doc=primary_doc,
            attachments=attachments,
        )
        assistant = dict(assistant_msg)
        assistant.setdefault("status", "complete")
        self.finalize_turn(cid, turn_id=turn["turn_id"], assistant=assistant)
        return self.get(cid)

    def append_messages(self, cid: str, messages: list[dict]) -> dict:
        with self._lock:
            self._conversation_row(cid)
            now = _now()
            for m in messages:
                seq = self._next_seq(cid)
                self.conn.execute(
                    """
                    INSERT INTO messages(
                        id, conversation_id, seq, role, text, ts, status,
                        timeline_json, sources_json, total_duration_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, 'complete', ?, ?, ?)
                    """,
                    (
                        _new_id(),
                        cid,
                        seq,
                        m.get("role", "assistant"),
                        m.get("text", ""),
                        m.get("ts") or now,
                        _dumps(m.get("timeline")) if "timeline" in m else None,
                        _dumps(m.get("sources")) if "sources" in m else None,
                        m.get("total_duration_ms"),
                    ),
                )
            self.conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, cid)
            )
            self.conn.commit()
            return self._conv_to_dict(self._conversation_row(cid))

    def append_injected_user_message(
        self,
        cid: str,
        *,
        text: str,
        client_message_id: str,
        doc_context: list | None = None,
        primary_doc: str | None = None,
        attachments: list[str] | None = None,
    ) -> dict:
        """Persist a mid-turn injected user message (seq before finalize assistant)."""
        with self._lock:
            self._conversation_row(cid)
            msg_id = _new_id()
            seq = self._next_seq(cid)
            now = _now()
            self.conn.execute(
                """
                INSERT INTO messages(
                    id, conversation_id, seq, role, text, ts, status,
                    client_message_id, doc_context_json, attachments_json, primary_doc
                ) VALUES (?, ?, ?, 'user', ?, ?, 'complete', ?, ?, ?, ?)
                """,
                (
                    msg_id,
                    cid,
                    seq,
                    text,
                    now,
                    client_message_id,
                    _dumps(doc_context),
                    _dumps(attachments),
                    primary_doc,
                ),
            )
            self.conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, cid)
            )
            self.conn.commit()
            row = self.conn.execute(
                "SELECT * FROM messages WHERE id = ?", (msg_id,)
            ).fetchone()
            return self._message_row_to_dict(row)
    def mark_question_resolved(
        self, cid: str, question_id: str, choice_label: str
    ) -> None:
        """把某条 ask_user 征询块标记为已选择，持久化用户的选择（便于重载后展示）。"""
        with self._lock:
            try:
                self._conversation_row(cid)
            except KeyError:
                return
            rows = self.conn.execute(
                """
                SELECT id, timeline_json FROM messages
                WHERE conversation_id = ? AND timeline_json IS NOT NULL
                """,
                (cid,),
            ).fetchall()
            changed = False

            def patch(blocks: list) -> bool:
                local_changed = False
                for block in blocks:
                    if (
                        block.get("type") == "tool"
                        and block.get("tool") in ("ask_user", "sandbox_run")
                        and block.get("question_id") == question_id
                    ):
                        block["choice_resolved"] = choice_label
                        local_changed = True
                    elif block.get("type") == "parallel":
                        if patch(block.get("children", [])):
                            local_changed = True
                return local_changed

            for row in rows:
                timeline = _loads(row["timeline_json"], [])
                if patch(timeline):
                    changed = True
                    self.conn.execute(
                        "UPDATE messages SET timeline_json = ? WHERE id = ?",
                        (_dumps(timeline), row["id"]),
                    )
            if changed:
                self.conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (_now(), cid),
                )
                self.conn.commit()

    def mark_summarized(self, cid: str, summary_path: str) -> None:
        with self._lock:
            self._conversation_row(cid)
            self.conn.execute(
                """
                UPDATE conversation_summaries SET is_primary = 0
                WHERE conversation_id = ? AND is_primary = 1
                """,
                (cid,),
            )
            last_msg = self.conn.execute(
                """
                SELECT id FROM messages WHERE conversation_id = ?
                ORDER BY seq DESC LIMIT 1
                """,
                (cid,),
            ).fetchone()
            max_rev = self.conn.execute(
                """
                SELECT COALESCE(MAX(revision), 0) AS n FROM conversation_summaries
                WHERE conversation_id = ? AND doc_path = ?
                """,
                (cid, summary_path),
            ).fetchone()["n"]
            self.conn.execute(
                """
                INSERT INTO conversation_summaries(
                    conversation_id, doc_path, revision, covered_through_message_id,
                    status, is_primary, created_at
                ) VALUES (?, ?, ?, ?, 'current', 1, ?)
                """,
                (
                    cid,
                    summary_path,
                    int(max_rev) + 1,
                    last_msg["id"] if last_msg else None,
                    _now(),
                ),
            )
            now = _now()
            self.conn.execute(
                "UPDATE conversations SET indexed_dirty = 0, updated_at = ? WHERE id = ?",
                (now, cid),
            )
            # 归档完成：立刻调度会话级记忆抽取（规格：归档即时）
            self._request_immediate_memory_extract_unlocked(cid, at=now)
            self.conn.commit()

    def _list_summaries_unlocked(self, cid: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM conversation_summaries
            WHERE conversation_id = ? ORDER BY revision ASC
            """,
            (cid,),
        ).fetchall()
        return [
            {
                "conversation_id": r["conversation_id"],
                "doc_path": r["doc_path"],
                "revision": r["revision"],
                "covered_through_message_id": r["covered_through_message_id"],
                "status": r["status"],
                "is_primary": bool(r["is_primary"]),
            }
            for r in rows
        ]

    def list_summaries(self, cid: str) -> list[dict]:
        with self._lock:
            self._conversation_row(cid)
            return self._list_summaries_unlocked(cid)

    def clear_dirty(self, cid: str) -> None:
        with self._lock:
            try:
                row = self._conversation_row(cid)
            except KeyError:
                return
            if row["indexed_dirty"]:
                self.conn.execute(
                    "UPDATE conversations SET indexed_dirty = 0 WHERE id = ?", (cid,)
                )
                self.conn.commit()

    # ------------------------------------------------------------------
    # derivation_outbox：派生任务队列（index_fts 等）
    # ------------------------------------------------------------------

    def claim_outbox(
        self, kind: str, limit: int = 10, lease_seconds: int = 60
    ) -> list[dict]:
        """认领待处理（或租约已过期）的 outbox 任务，标记为 running 并返回。"""
        return self._outbox.claim(kind, limit=limit, lease_seconds=lease_seconds)

    def complete_outbox(self, job_id: int) -> None:
        self._outbox.complete(job_id)

    def fail_outbox(self, job_id: int, error: str, backoff: float = 1.0) -> None:
        """失败重试：指数退避（backoff * 2^(attempts-1)），超过最大次数后置为 dead。"""
        self._outbox.fail(job_id, error, backoff=backoff)

    def list_outbox(
        self,
        *,
        kind: str | None = None,
        message_id: str | None = None,
    ) -> list[dict]:
        return self._outbox.list_jobs(kind=kind, message_id=message_id)

    def append_system_event(self, conversation_id: str, event_type: str, payload: dict) -> dict:
        event_id = _new_id()
        created_at = _now()
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO conversation_system_events(
                    id, conversation_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, conversation_id, event_type, _dumps(payload), created_at),
            )
            self.conn.commit()
        return {"id": event_id, "event_type": event_type, "payload": payload, "created_at": created_at}

    def list_system_events(
        self, conversation_id: str, *, after_event_id: str | None = None, limit: int = 50
    ) -> list[dict]:
        with self._lock:
            if after_event_id:
                anchor = self.conn.execute(
                    "SELECT rowid FROM conversation_system_events WHERE id = ?",
                    (after_event_id,),
                ).fetchone()
                if anchor is None:
                    return []
                rows = self.conn.execute(
                    """
                    SELECT * FROM conversation_system_events
                    WHERE conversation_id = ? AND rowid > ?
                    ORDER BY rowid ASC LIMIT ?
                    """,
                    (conversation_id, anchor["rowid"], limit),
                ).fetchall()
            else:
                rows = self.conn.execute(
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

    def get_message(self, message_id: str) -> dict | None:
        """加载消息及所属会话标题，供派生索引使用。"""
        with self._lock:
            row = self.conn.execute(
                """
                SELECT m.*, c.title AS conversation_title
                FROM messages m JOIN conversations c ON c.id = m.conversation_id
                WHERE m.id = ?
                """,
                (message_id,),
            ).fetchone()
            if row is None:
                return None
            msg = self._message_row_to_dict(row)
            msg["conversation_id"] = row["conversation_id"]
            msg["conversation_title"] = row["conversation_title"]
            return msg

    # ------------------------------------------------------------------
    # 迁移：旧版单文件 conversations.json → SQLite（一次性、幂等）
    # ------------------------------------------------------------------

    def _migrate_legacy_single_file(self, legacy_path: Path) -> None:
        data = json.loads(legacy_path.read_text(encoding="utf-8"))
        with self._lock:
            already = self.conn.execute(
                "SELECT value FROM migration_meta WHERE key = 'legacy_single_file'"
            ).fetchone()
            if already is None:
                for cid, conv in data.items():
                    created_at = conv.get("created_at") or _now()
                    updated_at = conv.get("updated_at") or created_at
                    self.conn.execute(
                        """
                        INSERT OR IGNORE INTO conversations(
                            id, title, created_at, updated_at, active_turn_id, indexed_dirty
                        ) VALUES (?, ?, ?, ?, NULL, ?)
                        """,
                        (
                            cid,
                            conv.get("title") or "新对话",
                            created_at,
                            updated_at,
                            int(bool(conv.get("indexed_dirty"))),
                        ),
                    )
                    last_user_msg_id = None
                    for seq, msg in enumerate(conv.get("messages", []), start=1):
                        role = msg.get("role", "user")
                        msg_id = _new_id()
                        ts = msg.get("ts") or created_at
                        in_reply_to = None
                        if role == "assistant" and last_user_msg_id:
                            in_reply_to = last_user_msg_id
                        self.conn.execute(
                            """
                            INSERT INTO messages(
                                id, conversation_id, seq, role, text, ts, status,
                                in_reply_to_message_id, timeline_json, sources_json,
                                total_duration_ms, doc_context_json, attachments_json,
                                primary_doc
                            ) VALUES (?, ?, ?, ?, ?, ?, 'complete', ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                msg_id,
                                cid,
                                seq,
                                role,
                                msg.get("text", ""),
                                ts,
                                in_reply_to,
                                _dumps(msg.get("timeline")) if "timeline" in msg else None,
                                _dumps(msg.get("sources")) if "sources" in msg else None,
                                msg.get("total_duration_ms"),
                                _dumps(msg.get("doc_context")) if "doc_context" in msg else None,
                                _dumps(msg.get("attachments")) if "attachments" in msg else None,
                                msg.get("primary_doc"),
                            ),
                        )
                        if role == "user":
                            last_user_msg_id = msg_id
                    if conv.get("summarized") and conv.get("summary_path"):
                        self.conn.execute(
                            """
                            INSERT INTO conversation_summaries(
                                conversation_id, doc_path, revision, covered_through_message_id,
                                status, is_primary, created_at
                            ) VALUES (?, ?, 1, NULL, 'current', 1, ?)
                            """,
                            (cid, conv["summary_path"], conv.get("summarized_at") or _now()),
                        )
            self.conn.execute(
                "INSERT OR REPLACE INTO migration_meta(key, value) VALUES ('legacy_single_file', ?)",
                (_now(),),
            )
            self.conn.commit()
        legacy_path.rename(legacy_path.with_suffix(".json.bak"))

    # ------------------------------------------------------------------
    # 文本视图：供归档总结 / 全文索引 / LLM 历史使用
    # ------------------------------------------------------------------

    @classmethod
    def _message_transcript_line(cls, msg: dict) -> str:
        role = msg.get("role")
        if role == "user":
            text = (msg.get("text") or "").strip()
            return f"【用户】{text}" if text else ""
        if role == "assistant":
            parts: list[str] = []
            text = cls._assistant_content(msg)
            if text:
                parts.append(f"【助手】{text}")
            parts.extend(cls._iter_kb_web_sources(msg))
            return "\n".join(parts)
        return ""

    @classmethod
    def iter_transcript_segments(cls, conv: dict, *, max_chars: int) -> Iterable[dict]:
        batch: list[dict] = []
        used = 0
        for msg in conv.get("messages", []):
            if msg.get("role") not in ("user", "assistant"):
                continue
            piece = cls._message_transcript_line(msg)
            if not piece:
                continue
            plen = len(piece)
            if batch and used + plen > max_chars:
                yield {
                    "messages": batch,
                    "first_message_id": batch[0]["id"],
                    "last_message_id": batch[-1]["id"],
                    "text": "\n\n".join(cls._message_transcript_line(m) for m in batch),
                }
                batch, used = [], 0
            batch.append(msg)
            used += plen + 2
        if batch:
            yield {
                "messages": batch,
                "first_message_id": batch[0]["id"],
                "last_message_id": batch[-1]["id"],
                "text": "\n\n".join(cls._message_transcript_line(m) for m in batch),
            }

    @classmethod
    def full_transcript(cls, conv: dict, *, max_chars: int = 60000) -> str:
        """整段会话稿：用于归档总结（通读全文，不做轮次截断，仅总长兜底）。"""
        lines: list[str] = []
        for msg in conv.get("messages", []):
            role = msg.get("role")
            if role == "user":
                text = (msg.get("text") or "").strip()
                if text:
                    lines.append(f"【用户】{text}")
            elif role == "assistant":
                text = cls._assistant_content(msg)
                if text:
                    lines.append(f"【助手】{text}")
                for src in cls._iter_kb_web_sources(msg):
                    lines.append(src)
        text = "\n\n".join(lines)
        if len(text) > max_chars:
            text = text[-max_chars:]
        return text

    @classmethod
    def conversation_text(cls, conv: dict, *, max_chars: int = 20000) -> str:
        """会话可检索正文（喂给全文索引）：仅用户与助手文字，去掉工具噪声。"""
        lines: list[str] = []
        for msg in conv.get("messages", []):
            role = msg.get("role")
            if role == "user":
                text = (msg.get("text") or "").strip()
                if text:
                    lines.append(text)
            elif role == "assistant":
                text = cls._assistant_content(msg)
                if text:
                    lines.append(text)
        text = "\n\n".join(lines)
        return text[:max_chars] if len(text) > max_chars else text

    @staticmethod
    def _iter_kb_web_sources(msg: dict) -> list[str]:
        out: list[str] = []
        for src in msg.get("sources") or []:
            st = src.get("type")
            if st == "web" or st == "search":
                title = src.get("title") or src.get("url") or ""
                snippet = (src.get("snippet") or "").strip()
                if title:
                    out.append(f"（来源：{title}）{snippet}".strip())
            elif st == "kb":
                path = src.get("path")
                if path:
                    out.append(f"（本地：{path}）")
        return out

    @staticmethod
    def _assistant_content(msg: dict) -> str:
        if msg.get("text"):
            return str(msg["text"]).strip()
        parts: list[str] = []
        for block in msg.get("timeline") or []:
            if block.get("type") == "text" and block.get("content"):
                part = str(block["content"]).strip()
                if part:
                    parts.append(part)
        return "\n\n".join(parts)

    @classmethod
    def llm_history(
        cls,
        conv: dict,
        *,
        max_turns: int = 20,
        max_chars: int = 32000,
    ) -> list[dict]:
        """将已保存的对话转为 LLM 多轮 messages（不含本轮尚未保存的用户消息）。"""
        candidates: list[dict] = []
        for msg in conv.get("messages", []):
            role = msg.get("role")
            if role == "user":
                text = (msg.get("text") or "").strip()
                if text:
                    candidates.append({"role": "user", "content": text})
            elif role == "assistant":
                text = cls._assistant_content(msg)
                if text:
                    candidates.append({"role": "assistant", "content": text})

        user_indices = [i for i, m in enumerate(candidates) if m["role"] == "user"]
        if len(user_indices) > max_turns:
            candidates = candidates[user_indices[-max_turns] :]

        while candidates:
            total = sum(len(m["content"]) for m in candidates)
            if total <= max_chars:
                break
            candidates.pop(0)
        return candidates

    @staticmethod
    def context_excerpt(conv: dict, *, max_chars: int = 4000) -> str:
        lines: list[str] = []
        for msg in conv.get("messages", [])[-8:]:
            role = msg.get("role")
            if role == "user" and msg.get("text"):
                lines.append(f"用户：{msg['text']}")
            elif role == "assistant":
                text = ConversationStore._assistant_content(msg)
                if text:
                    lines.append(f"助手：{text[:800]}")
                elif msg.get("timeline"):
                    for block in msg["timeline"]:
                        if block.get("type") == "tool" and block.get("tool") in (
                            "ask_user",
                            "sandbox_run",
                        ):
                            q = block.get("question") or block.get("summary") or ""
                            if q:
                                lines.append(f"助手征询：{q}")
        text = "\n".join(lines)
        return text[:max_chars] if len(text) > max_chars else text
