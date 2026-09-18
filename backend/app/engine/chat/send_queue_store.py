"""服务端发送队列：按会话持久化，客户端仅作展示与编辑。

跨端语义：队列条目存服务端 DB；任一客户端排队后，注入与续发由
服务端在回合边界执行（见 usage 侧 drain 钩子），浏览器关闭不影响。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS send_queue_items (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    text TEXT NOT NULL,
    timing TEXT NOT NULL DEFAULT 'defer',
    doc_context TEXT,
    primary_doc TEXT,
    attachments TEXT,
    web_enabled INTEGER NOT NULL DEFAULT 0,
    mentions TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_send_queue_conv
    ON send_queue_items(conversation_id, seq);
CREATE TABLE IF NOT EXISTS send_queue_state (
    conversation_id TEXT PRIMARY KEY,
    paused INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""


class SendQueueStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(_SCHEMA)

    def list_items(self, conversation_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM send_queue_items
                 WHERE conversation_id = ?
                 ORDER BY seq
                """,
                (conversation_id,),
            ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def is_paused(self, conversation_id: str) -> bool:
        with self._lock:
            row = self.conn.execute(
                "SELECT paused FROM send_queue_state WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        return bool(row and row["paused"])

    def set_paused(self, conversation_id: str, paused: bool) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO send_queue_state (conversation_id, paused, updated_at)
                 VALUES (?, ?, ?)
                 ON CONFLICT(conversation_id) DO UPDATE
                   SET paused = excluded.paused, updated_at = excluded.updated_at
                """,
                (conversation_id, 1 if paused else 0, _now()),
            )
            self.conn.commit()

    def enqueue(
        self, conversation_id: str, item: dict[str, Any]
    ) -> dict[str, Any]:
        created = _now()
        with self._lock:
            seq_row = self.conn.execute(
                """
                SELECT COALESCE(MAX(seq), -1) + 1 AS seq
                  FROM send_queue_items
                 WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
            item = {
                "id": item.get("id") or uuid.uuid4().hex,
                "conversation_id": conversation_id,
                "text": item.get("text") or "",
                "timing": item.get("timing") or "defer",
                "doc_context": _dump(item.get("doc_context")),
                "primary_doc": item.get("primary_doc"),
                "attachments": _dump(item.get("attachments")),
                "web_enabled": 1 if item.get("web_enabled") else 0,
                "mentions": _dump(item.get("mentions")),
                "status": "queued",
                "error": None,
                "created_at": created,
                "seq": seq_row["seq"],
            }
            self.conn.execute(
                """
                INSERT INTO send_queue_items (
                    id, conversation_id, seq, text, timing, doc_context,
                    primary_doc, attachments, web_enabled, mentions,
                    status, error, created_at
                ) VALUES (
                    :id, :conversation_id, :seq, :text, :timing, :doc_context,
                    :primary_doc, :attachments, :web_enabled, :mentions,
                    :status, :error, :created_at
                )
                """,
                item,
            )
            self.conn.commit()
        return self.get(conversation_id, item["id"])

    def get(
        self, conversation_id: str, item_id: str
    ) -> dict[str, Any] | None:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT * FROM send_queue_items
                 WHERE conversation_id = ? AND id = ?
                """,
                (conversation_id, item_id),
            ).fetchone()
        return self._row_to_item(row) if row else None

    def update(
        self, conversation_id: str, item_id: str, patch: dict[str, Any]
    ) -> dict[str, Any] | None:
        fields: list[str] = []
        params: list[Any] = []
        if "text" in patch:
            fields.append("text = ?")
            params.append(patch["text"] or "")
        if "timing" in patch:
            fields.append("timing = ?")
            params.append(patch["timing"])
        if "error" in patch:
            fields.append("error = ?")
            params.append(patch["error"])
        if not fields:
            return self.get(conversation_id, item_id)
        params.extend([conversation_id, item_id])
        with self._lock:
            self.conn.execute(
                f"""
                UPDATE send_queue_items
                   SET {', '.join(fields)}
                 WHERE conversation_id = ? AND id = ?
                """,
                params,
            )
            self.conn.commit()
        return self.get(conversation_id, item_id)

    def remove(self, conversation_id: str, item_id: str) -> None:
        with self._lock:
            self.conn.execute(
                """
                DELETE FROM send_queue_items
                 WHERE conversation_id = ? AND id = ?
                """,
                (conversation_id, item_id),
            )
            self.conn.commit()

    def clear(self, conversation_id: str) -> None:
        with self._lock:
            self.conn.execute(
                "DELETE FROM send_queue_items WHERE conversation_id = ?",
                (conversation_id,),
            )
            self.conn.commit()

    def move(
        self, conversation_id: str, item_id: str, direction: -1 | 1
    ) -> None:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT id, seq FROM send_queue_items
                 WHERE conversation_id = ?
                 ORDER BY seq, created_at
                """,
                (conversation_id,),
            ).fetchall()
            ids = [r["id"] for r in rows]
            if item_id not in ids:
                return
            i = ids.index(item_id)
            j = i + direction
            if j < 0 or j >= len(ids):
                return
            ids[i], ids[j] = ids[j], ids[i]
            for seq, iid in enumerate(ids):
                self.conn.execute(
                    "UPDATE send_queue_items SET seq = ? WHERE id = ?",
                    (seq, iid),
                )
            self.conn.commit()

    def move_to_front(self, conversation_id: str, item_id: str) -> None:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT id FROM send_queue_items
                 WHERE conversation_id = ?
                 ORDER BY seq, created_at
                """,
                (conversation_id,),
            ).fetchall()
            ids = [r["id"] for r in rows]
            if item_id not in ids:
                return
            ids.remove(item_id)
            ids.insert(0, item_id)
            for seq, iid in enumerate(ids):
                self.conn.execute(
                    "UPDATE send_queue_items SET seq = ? WHERE id = ?",
                    (seq, iid),
                )
            self.conn.commit()

    def _row_to_item(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "text": row["text"],
            "timing": row["timing"],
            "doc_context": _load(row["doc_context"]),
            "primary_doc": row["primary_doc"],
            "attachments": _load(row["attachments"]),
            "web_enabled": bool(row["web_enabled"]),
            "mentions": _load(row["mentions"]),
            "status": row["status"],
            "error": row["error"],
            "created_at": row["created_at"],
        }


def _dump(value: Any) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value else None


def _load(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None
