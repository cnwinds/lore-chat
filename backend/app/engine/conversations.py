from __future__ import annotations

import json
from collections.abc import Callable, Iterable
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path

from app.engine.conversation.deletion import ConversationDeletionWorkflow
from app.engine.conversation.memory_schedule import MemoryExtractSchedule
from app.engine.conversation.message_graph import ConversationMessageGraph
from app.engine.conversation.summary_ledger import ConversationSummaryLedger
from app.engine.conversation.system_events import ConversationSystemEvents
from app.engine.conversation.transcript import ConversationTranscript
from app.engine.conversation.outbox import DerivationOutbox
from app.engine.conversation.shared import (
    TurnInProgress,
    dumps_json as _dumps,
    loads_json as _loads,
    new_id as _new_id,
    now_iso as _now,
    title_from_text as _title_from_text,
)
from app.engine.conversation.turn_lifecycle import TurnLifecycle


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
    primary_doc TEXT,
    model_name TEXT,
    model_failover INTEGER NOT NULL DEFAULT 0,
    web_enabled INTEGER
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
            self._ensure_message_model_columns()
            self._ensure_message_web_enabled_column()
            self.conn.commit()

        if legacy_single.exists():
            self._migrate_legacy_single_file(legacy_single)

        if (self.dir / "index.json").exists() and not self._json_shards_migrated():
            from .conversation_migrate import migrate_json_shards

            migrate_json_shards(self.dir)

        self._outbox = DerivationOutbox(self.conn, self._lock)
        self.memory_schedule = MemoryExtractSchedule(
            self.conn, self._lock, self._outbox
        )
        self._turn_lifecycle = TurnLifecycle(self)
        self.message_graph = ConversationMessageGraph(self)
        self.deletion = ConversationDeletionWorkflow(self)
        self.summaries = ConversationSummaryLedger(self)
        self.system_events = ConversationSystemEvents(self)

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

    def _ensure_message_model_columns(self) -> None:
        cols = {
            r[1]
            for r in self.conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "model_name" not in cols:
            self.conn.execute("ALTER TABLE messages ADD COLUMN model_name TEXT")
        if "model_failover" not in cols:
            self.conn.execute(
                "ALTER TABLE messages ADD COLUMN model_failover INTEGER NOT NULL DEFAULT 0"
            )

    def _ensure_message_web_enabled_column(self) -> None:
        cols = {
            r[1]
            for r in self.conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "web_enabled" not in cols:
            self.conn.execute("ALTER TABLE messages ADD COLUMN web_enabled INTEGER")

    def _json_shards_migrated(self) -> bool:
        row = self.conn.execute(
            "SELECT value FROM migration_meta WHERE key = 'json_shards_v1'"
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # 记忆抽取调度（委托 MemoryExtractSchedule）
    # ------------------------------------------------------------------

    def _mark_memory_dirty_unlocked(self, cid: str, *, at: str | None = None) -> None:
        self.memory_schedule.mark_dirty_unlocked(cid, at=at)

    def mark_memory_dirty(self, cid: str, *, at: str | None = None) -> None:
        self.memory_schedule.mark_dirty(cid, at=at)

    def get_last_user_message_at(self, cid: str) -> str | None:
        return self.memory_schedule.get_last_user_message_at(cid)

    def clear_memory_dirty(
        self,
        cid: str,
        *,
        at: str | None = None,
        expected_last_user_message_at: str | None = None,
    ) -> int | None:
        return self.memory_schedule.clear_dirty(
            cid,
            at=at,
            expected_last_user_message_at=expected_last_user_message_at,
        )

    def get_memory_extract_revision(self, cid: str) -> int:
        return self.memory_schedule.get_extract_revision(cid)

    def _enqueue_session_observe_unlocked(
        self, conversation_id: str, *, immediate: bool = False
    ) -> bool:
        return self.memory_schedule.enqueue_session_observe_unlocked(
            conversation_id, immediate=immediate
        )

    def enqueue_session_observe(
        self, conversation_id: str, *, immediate: bool = False
    ) -> bool:
        return self.memory_schedule.enqueue_session_observe(
            conversation_id, immediate=immediate
        )

    def batch_mark_dirty_and_enqueue_session_observe(
        self,
        conversation_ids: list[str],
        *,
        mark_dirty: bool = True,
        immediate: bool = False,
    ) -> int:
        return self.memory_schedule.batch_mark_dirty_and_enqueue(
            conversation_ids,
            mark_dirty=mark_dirty,
            immediate=immediate,
        )

    def cancel_legacy_observe_memory(self) -> int:
        return self.memory_schedule.cancel_legacy_observe_memory()

    def is_memory_extract_idle(self, cid: str, *, idle_hours: float = 24.0) -> bool:
        return self.memory_schedule.is_extract_idle(cid, idle_hours=idle_hours)

    def _request_immediate_memory_extract_unlocked(self, cid: str) -> bool:
        return self.memory_schedule.request_immediate_unlocked(cid)

    def request_immediate_memory_extract(self, cid: str) -> bool:
        return self.memory_schedule.request_immediate(cid)

    def consume_memory_immediate_pending_if_dirty(self, cid: str) -> bool:
        return self.memory_schedule.consume_immediate_pending(cid)

    def list_idle_dirty_conversations(
        self, *, idle_hours: float = 24.0, limit: int = 20
    ) -> list[dict]:
        return self.memory_schedule.list_idle_dirty(
            idle_hours=idle_hours, limit=limit
        )

    def list_conversation_ids(self) -> list[str]:
        with self._lock:
            rows = self.conn.execute("SELECT id FROM conversations").fetchall()
            return [r["id"] for r in rows]

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
        elif msg.get("timeline"):
            # 兼容旧行：finalize 曾未写 attachments_json，从时间线工具块回填
            from app.engine.chat.timeline import collect_timeline_attachments

            atts = collect_timeline_attachments(msg["timeline"])
            if atts:
                msg["attachments"] = atts
        if row["primary_doc"]:
            msg["primary_doc"] = row["primary_doc"]
        try:
            if row["model_name"]:
                msg["model_name"] = row["model_name"]
        except (KeyError, IndexError):
            pass
        try:
            if row["model_failover"]:
                msg["model_failover"] = True
        except (KeyError, IndexError):
            pass
        try:
            if row["web_enabled"] is not None:
                msg["web_enabled"] = bool(row["web_enabled"])
        except (KeyError, IndexError):
            pass
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
        return self.summaries.summary_state(cid)

    def _conversation_row(self, cid: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (cid,)
        ).fetchone()
        if row is None:
            raise KeyError(cid)
        return row

    def _conv_to_dict(self, row: sqlite3.Row) -> dict:
        cid = row["id"]
        summarized, summary_path, summarized_at = self.summaries.summary_state(cid)
        summaries = self.summaries.list_unlocked(cid)
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
        self.summaries.mark_stale_unlocked(cid)

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

    def get_active_turn_meta(self, cid: str) -> dict:
        """Lightweight active turn snapshot (no messages)."""
        with self._lock:
            row = self._conversation_row(cid)
            active_turn_id = row["active_turn_id"]
            if not active_turn_id:
                return {
                    "conversation_id": cid,
                    "turn_id": None,
                    "status": None,
                    "started_at": None,
                }
            trow = self.conn.execute(
                "SELECT id, status, started_at FROM turns WHERE id = ?",
                (active_turn_id,),
            ).fetchone()
            if trow is None:
                return {
                    "conversation_id": cid,
                    "turn_id": active_turn_id,
                    "status": None,
                    "started_at": None,
                }
            return {
                "conversation_id": cid,
                "turn_id": trow["id"],
                "status": trow["status"],
                "started_at": trow["started_at"],
            }

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

    def delete(
        self,
        cid: str,
        *,
        conversation_fts=None,
        conversation_vector=None,
        indexer=None,
        index_revision=None,
        ledger_path: str | Path | None = None,
        delete_summary: bool = True,
    ) -> None:
        """兼容委托：协议见 ConversationDeletionWorkflow。"""
        self.deletion.delete(
            cid,
            conversation_fts=conversation_fts,
            conversation_vector=conversation_vector,
            indexer=indexer,
            index_revision=index_revision,
            ledger_path=ledger_path,
            delete_summary=delete_summary,
        )

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
        web_enabled: bool | None = None,
        reuse_user_message_id: str | None = None,
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
            web_enabled=web_enabled,
            reuse_user_message_id=reuse_user_message_id,
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
        return self.message_graph.append_messages(cid, messages)

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
        return self.message_graph.append_injected_user_message(
            cid,
            text=text,
            client_message_id=client_message_id,
            doc_context=doc_context,
            primary_doc=primary_doc,
            attachments=attachments,
        )

    def mark_question_resolved(
        self, cid: str, question_id: str, choice_label: str
    ) -> None:
        """把某条 ask_user 征询块标记为已选择，持久化用户的选择（便于重载后展示）。"""
        self.message_graph.mark_question_resolved(cid, question_id, choice_label)

    def latest_message_id_unlocked(self, cid: str) -> str | None:
        """当前会话最新消息 id（摘要覆盖终点）；调用方已持锁。"""
        row = self.conn.execute(
            """
            SELECT id FROM messages WHERE conversation_id = ?
            ORDER BY seq DESC LIMIT 1
            """,
            (cid,),
        ).fetchone()
        return row["id"] if row else None

    def notify_archived_unlocked(self, cid: str) -> None:
        """归档落库后的记忆即时调度钩子；调用方已持锁。

        不传用户消息时钟：立即重抽不得推进 last_user_message_at。
        """
        self.memory_schedule.request_immediate_unlocked(cid)

    def mark_summarized(self, cid: str, summary_path: str) -> None:
        """兼容委托 → summaries.mark_summarized。"""
        self.summaries.mark_summarized(cid, summary_path)

    def list_summaries(self, cid: str) -> list[dict]:
        """兼容委托 → summaries.list_summaries。"""
        return self.summaries.list_summaries(cid)

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
        """兼容委托 → system_events.append。"""
        return self.system_events.append(conversation_id, event_type, payload)

    def list_system_events(
        self, conversation_id: str, *, after_event_id: str | None = None, limit: int = 50
    ) -> list[dict]:
        """兼容委托 → system_events.list。"""
        return self.system_events.list(
            conversation_id, after_event_id=after_event_id, limit=limit
        )

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

    def transform_message_json_columns(
        self,
        transform: Callable[[str | None], str | None],
        *,
        columns: tuple[str, ...] = ("attachments_json", "timeline_json"),
    ) -> int:
        """对全部消息的指定 JSON 文本列做幂等变换。返回更新行数。"""
        if not columns:
            return 0
        col_sql = ", ".join(columns)
        updated = 0
        with self._lock:
            rows = self.conn.execute(
                f"SELECT id, {col_sql} FROM messages"
            ).fetchall()
            for row in rows:
                new_vals: list[str | None] = []
                changed = False
                for col in columns:
                    old = row[col]
                    new = transform(old)
                    new_vals.append(new)
                    if new != old:
                        changed = True
                if not changed:
                    continue
                sets = ", ".join(f"{c} = ?" for c in columns)
                self.conn.execute(
                    f"UPDATE messages SET {sets} WHERE id = ?",
                    (*new_vals, row["id"]),
                )
                updated += 1
            if updated:
                self.conn.commit()
        return updated

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
    # 文本视图（委托 ConversationTranscript）
    # ------------------------------------------------------------------

    @classmethod
    def iter_transcript_segments(cls, conv: dict, *, max_chars: int):
        return ConversationTranscript.iter_segments(conv, max_chars=max_chars)

    @classmethod
    def full_transcript(cls, conv: dict, *, max_chars: int = 60000) -> str:
        return ConversationTranscript.full(conv, max_chars=max_chars)

    @classmethod
    def conversation_text(cls, conv: dict, *, max_chars: int = 20000) -> str:
        return ConversationTranscript.indexable_text(conv, max_chars=max_chars)

    @classmethod
    def llm_history(
        cls,
        conv: dict,
        *,
        max_turns: int = 20,
        max_chars: int = 32000,
    ) -> list[dict]:
        return ConversationTranscript.llm_history(
            conv, max_turns=max_turns, max_chars=max_chars
        )

    @staticmethod
    def context_excerpt(conv: dict, *, max_chars: int = 4000) -> str:
        return ConversationTranscript.context_excerpt(conv, max_chars=max_chars)
