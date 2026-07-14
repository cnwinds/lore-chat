from __future__ import annotations

import json
from collections.abc import Iterable
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

MAX_OUTBOX_ATTEMPTS = 5


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _future(seconds: float) -> str:
    return (datetime.now() + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def _title_from_text(text: str) -> str:
    line = text.strip().split("\n")[0]
    if len(line) > 40:
        return line[:40] + "…"
    return line or "新对话"


def _new_id() -> str:
    return uuid.uuid4().hex


def _loads(raw: str | None, default):
    if not raw:
        return default
    return json.loads(raw)


def _dumps(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


class _ConversationFTSLike(Protocol):
    def delete_conversation(self, conversation_id: str) -> None: ...


class _ConversationVectorLike(Protocol):
    def delete_conversation(self, conversation_id: str) -> None: ...


class _IndexRevisionLike(Protocol):
    def bump(self) -> int: ...


class _IndexerLike(Protocol):
    def remove_conversation(self, cid: str) -> None: ...


class TurnInProgress(Exception):
    """本会话已存在一个 running turn，同一 client_message_id 不应再次触发 Agent。"""

    def __init__(self, turn_id: str, retry_after_ms: int = 1000):
        super().__init__(f"turn {turn_id} in progress")
        self.turn_id = turn_id
        self.retry_after_ms = retry_after_ms


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
            self.conn.commit()

        if legacy_single.exists():
            self._migrate_legacy_single_file(legacy_single)

        if (self.dir / "index.json").exists() and not self._json_shards_migrated():
            from .conversation_migrate import migrate_json_shards

            migrate_json_shards(self.dir)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _json_shards_migrated(self) -> bool:
        row = self.conn.execute(
            "SELECT value FROM migration_meta WHERE key = 'json_shards_v1'"
        ).fetchone()
        return row is not None

    def _next_seq(self, cid: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM messages WHERE conversation_id = ?",
            (cid,),
        ).fetchone()
        return int(row["n"])

    def _enqueue_index_jobs(self, message_id: str, turn_id: str | None) -> None:
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
            msg["doc_context"] = _loads(row["doc_context_json"], [])
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
        return {
            "id": cid,
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "active_turn_id": row["active_turn_id"],
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
        return self.dir.parent / "migrations" / "conversation-deletions.jsonl"

    @staticmethod
    def _append_deletion_ledger(
        path: Path, cid: str, deletion_id: str, deleted_at: str, options: dict
    ) -> None:
        """跨版本留存的删除凭据：追加 JSONL 行并 fsync，供历史回填/审计恢复使用。"""
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
        5. 通知旧版文档级 `Indexer` 清理遗留的 `conv:{cid}` FTS 记录。
        """
        with self._lock:
            self._conversation_row(cid)

        deletion_id = _new_id()
        deleted_at = _now()
        options = {"delete_summary": delete_summary}
        ledger_file = Path(ledger_path) if ledger_path else self._default_deletion_ledger_path()
        self._append_deletion_ledger(ledger_file, cid, deletion_id, deleted_at, options)

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
            self.conn.execute(
                """
                UPDATE derivation_outbox
                SET status = 'cancelled', updated_at = ?
                WHERE status IN ('pending', 'running')
                  AND (
                        turn_id IN (SELECT id FROM turns WHERE conversation_id = ?)
                        OR source_message_id IN (
                            SELECT id FROM messages WHERE conversation_id = ?
                        )
                  )
                """,
                (deleted_at, cid, cid),
            )
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
            conversation_vector.delete_conversation(cid)
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
        with self._lock:
            conv_row = self._conversation_row(cid)

            existing = self.conn.execute(
                "SELECT * FROM turns WHERE conversation_id = ? AND client_message_id = ?",
                (cid, client_message_id),
            ).fetchone()
            if existing is not None:
                if existing["status"] == "running":
                    raise TurnInProgress(existing["id"])
                user_row = self.conn.execute(
                    "SELECT * FROM messages WHERE id = ?",
                    (existing["user_message_id"],),
                ).fetchone()
                result: dict = {
                    "turn_id": existing["id"],
                    "status": existing["status"],
                    "user_message": self._message_row_to_dict(user_row),
                }
                if existing["assistant_message_id"]:
                    assistant_row = self.conn.execute(
                        "SELECT * FROM messages WHERE id = ?",
                        (existing["assistant_message_id"],),
                    ).fetchone()
                    if assistant_row is not None:
                        result["assistant_message"] = self._message_row_to_dict(
                            assistant_row
                        )
                return result

            # 单个会话同一时间只允许一个 active turn（spec §6.1）：不同
            # client_message_id 但会话已有 running turn 时，拒绝开启新 turn。
            if conv_row["active_turn_id"]:
                active_turn = self.conn.execute(
                    "SELECT * FROM turns WHERE id = ?",
                    (conv_row["active_turn_id"],),
                ).fetchone()
                if active_turn is not None and active_turn["status"] == "running":
                    raise TurnInProgress(active_turn["id"])

            now = user_ts or _now()
            msg_id = _new_id()
            seq = self._next_seq(cid)
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
                    user_text,
                    now,
                    client_message_id,
                    _dumps(doc_context),
                    _dumps(attachments),
                    primary_doc,
                ),
            )

            turn_id = _new_id()
            started_at = _now()
            self.conn.execute(
                """
                INSERT INTO turns(
                    id, conversation_id, client_message_id, user_message_id,
                    assistant_message_id, status, observation_allowed,
                    started_at
                ) VALUES (?, ?, ?, ?, NULL, 'running', ?, ?)
                """,
                (turn_id, cid, client_message_id, msg_id, int(observation_allowed), started_at),
            )

            self._enqueue_index_jobs(msg_id, turn_id)
            self._mark_dirty_and_stale(cid)

            title = conv_row["title"]
            if title == "新对话" and user_text.strip():
                self.conn.execute(
                    "UPDATE conversations SET title = ? WHERE id = ?",
                    (_title_from_text(user_text), cid),
                )

            self.conn.execute(
                "UPDATE conversations SET active_turn_id = ?, updated_at = ? WHERE id = ?",
                (turn_id, started_at, cid),
            )
            self.conn.commit()

            msg_row = self.conn.execute(
                "SELECT * FROM messages WHERE id = ?", (msg_id,)
            ).fetchone()
            return {
                "turn_id": turn_id,
                "status": "running",
                "user_message": self._message_row_to_dict(msg_row),
            }

    def finalize_turn(self, cid: str, turn_id: str, assistant: dict) -> dict | None:
        with self._lock:
            self._conversation_row(cid)
            turn = self.conn.execute(
                "SELECT * FROM turns WHERE id = ? AND conversation_id = ?",
                (turn_id, cid),
            ).fetchone()
            if turn is None:
                raise KeyError(turn_id)

            if turn["status"] != "running":
                # 幂等：已 finalize 过的 turn 不再插入第二条助手消息。
                if turn["assistant_message_id"]:
                    msg_row = self.conn.execute(
                        "SELECT * FROM messages WHERE id = ?",
                        (turn["assistant_message_id"],),
                    ).fetchone()
                    if msg_row is not None:
                        return self._message_row_to_dict(msg_row)
                return None

            status = assistant.get("status") or "complete"
            has_content = bool(
                assistant.get("text")
                or assistant.get("timeline")
                or assistant.get("sources")
                or assistant.get("error")
            )

            assistant_msg_id = None
            result: dict | None = None
            if has_content:
                assistant_msg_id = _new_id()
                seq = self._next_seq(cid)
                now = assistant.get("ts") or _now()
                self.conn.execute(
                    """
                    INSERT INTO messages(
                        id, conversation_id, seq, role, text, ts, status,
                        in_reply_to_message_id, timeline_json, sources_json,
                        total_duration_ms
                    ) VALUES (?, ?, ?, 'assistant', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        assistant_msg_id,
                        cid,
                        seq,
                        assistant.get("text") or "",
                        now,
                        status,
                        turn["user_message_id"],
                        _dumps(assistant.get("timeline", [])),
                        _dumps(assistant.get("sources", [])),
                        assistant.get("total_duration_ms"),
                    ),
                )
                self._enqueue_index_jobs(assistant_msg_id, turn_id)
                msg_row = self.conn.execute(
                    "SELECT * FROM messages WHERE id = ?", (assistant_msg_id,)
                ).fetchone()
                result = self._message_row_to_dict(msg_row)

            turn_status = "complete" if status == "complete" else "interrupted"
            finalized_at = _now()
            self.conn.execute(
                """
                UPDATE turns SET assistant_message_id = ?, status = ?, finalized_at = ?
                WHERE id = ?
                """,
                (assistant_msg_id, turn_status, finalized_at, turn_id),
            )
            self.conn.execute(
                "UPDATE conversations SET active_turn_id = NULL, updated_at = ? WHERE id = ?",
                (finalized_at, cid),
            )
            self.conn.commit()
            return result

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
                        and block.get("tool") == "ask_user"
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
        with self._lock:
            now = _now()
            rows = self.conn.execute(
                """
                SELECT * FROM derivation_outbox
                WHERE kind = ?
                  AND (
                        status = 'pending'
                        OR (status = 'running' AND (locked_until IS NULL OR locked_until <= ?))
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

    def complete_outbox(self, job_id: int) -> None:
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

    def fail_outbox(self, job_id: int, error: str, backoff: float = 1.0) -> None:
        """失败重试：指数退避（backoff * 2^(attempts-1)），超过最大次数后置为 dead。"""
        with self._lock:
            row = self.conn.execute(
                "SELECT attempts FROM derivation_outbox WHERE id = ?", (job_id,)
            ).fetchone()
            if row is None:
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
                WHERE id = ?
                """,
                (attempts, status, next_run_at, error, _now(), job_id),
            )
            self.conn.commit()

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
                        if block.get("type") == "tool" and block.get("tool") == "ask_user":
                            q = block.get("question") or block.get("summary") or ""
                            if q:
                                lines.append(f"助手征询：{q}")
        text = "\n".join(lines)
        return text[:max_chars] if len(text) > max_chars else text
