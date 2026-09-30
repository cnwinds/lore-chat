"""主对话 LLM 请求快照存储。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import zlib
from datetime import datetime, timezone
from typing import Any

from app.engine.usage.request_segment import (
    message_text_content,
    sanitize_api_message,
    segment_meta_for_store,
    segments_for_api_message,
    segments_from_store_meta,
)
from app.logging_config import get_logger

_log = get_logger("request_log")

REQUEST_LOG_TURNS_PER_CONVERSATION = 10
REQUEST_LOG_MAX_CALLS = 3000

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS request_blobs (
  hash TEXT PRIMARY KEY,
  body BLOB NOT NULL,
  size INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS request_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id TEXT NOT NULL,
  turn_id TEXT NOT NULL,
  round INTEGER NOT NULL,
  ts TEXT NOT NULL,
  model TEXT,
  model_label TEXT,
  candidate_id TEXT,
  params_json TEXT NOT NULL,
  tools_hash TEXT,
  tool_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 1,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  cache_tokens INTEGER,
  duration_ms INTEGER,
  error TEXT,
  UNIQUE (conversation_id, turn_id, round)
);

CREATE TABLE IF NOT EXISTS request_call_messages (
  call_id INTEGER NOT NULL,
  idx INTEGER NOT NULL,
  hash TEXT NOT NULL,
  segments_json TEXT NOT NULL,
  PRIMARY KEY (call_id, idx)
);

CREATE INDEX IF NOT EXISTS request_call_messages_hash ON request_call_messages(hash);
CREATE INDEX IF NOT EXISTS request_calls_conv ON request_calls(conversation_id, ts);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _blob_hash(obj: Any) -> str:
    return hashlib.sha256(_canonical_json(obj).encode("utf-8")).hexdigest()


class RequestLogRecorder:
    """挂到 LLMClient.request_log；采集失败不影响回合。"""

    def __init__(self, store: RequestLogStore):
        self.store = store

    def begin(
        self,
        *,
        model: str | None,
        model_label: str | None,
        candidate_id: str | None,
        api_messages: list[dict],
        annotations: list[dict],
        tools: list[dict] | None,
        params: dict[str, Any],
    ) -> int | None:
        from app.engine.usage.request_capture import get_request_capture_context

        ctx = get_request_capture_context()
        if ctx is None:
            return None
        return self.store.begin(
            conversation_id=ctx.conversation_id,
            turn_id=ctx.turn_id,
            round=ctx.round,
            model=model,
            model_label=model_label,
            candidate_id=candidate_id,
            api_messages=api_messages,
            annotations=annotations,
            tools=tools,
            params=params,
        )

    def finish(
        self,
        call_id: int | None,
        *,
        status: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        cache_tokens: int | None = None,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        self.store.finish(
            call_id,
            status=status,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_tokens=cache_tokens,
            duration_ms=duration_ms,
            error=error,
        )


class RequestLogStore:
    def __init__(self, db_path):
        from pathlib import Path

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(_SCHEMA)
            self._migrate_schema()
            self.conn.commit()

    def _migrate_schema(self) -> None:
        cols = {
            r[1] for r in self.conn.execute("PRAGMA table_info(request_calls)").fetchall()
        }
        if "tool_count" not in cols:
            self.conn.execute(
                "ALTER TABLE request_calls ADD COLUMN tool_count INTEGER NOT NULL DEFAULT 0"
            )

    def close(self) -> None:
        with self._lock:
            if self.conn is not None:
                self.conn.close()
                self.conn = None

    def delete_conversation(self, conversation_id: str) -> None:
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, tools_hash FROM request_calls WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchall()
            if not rows:
                return
            call_ids = [int(r["id"]) for r in rows]
            tools_hashes = {r["tools_hash"] for r in rows if r["tools_hash"]}
            placeholders = ",".join("?" * len(call_ids))
            msg_hashes = {
                r["hash"]
                for r in self.conn.execute(
                    f"SELECT hash FROM request_call_messages WHERE call_id IN ({placeholders})",
                    call_ids,
                ).fetchall()
            }
            self.conn.execute(
                f"DELETE FROM request_call_messages WHERE call_id IN ({placeholders})",
                call_ids,
            )
            self.conn.execute(
                "DELETE FROM request_calls WHERE conversation_id = ?",
                (conversation_id,),
            )
            self._gc_blobs(msg_hashes | tools_hashes)
            self.conn.commit()

    def list_calls(self, conversation_id: str, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT c.*,
                  (SELECT COUNT(*) FROM request_call_messages m WHERE m.call_id = c.id) AS message_count
                FROM request_calls c
                WHERE c.conversation_id = ?
                ORDER BY c.ts DESC, c.id DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_call_row(
        self, conversation_id: str, call_id: int | str
    ) -> sqlite3.Row | None:
        with self._lock:
            if str(call_id) == "latest":
                return self.conn.execute(
                    """
                    SELECT * FROM request_calls
                    WHERE conversation_id = ?
                    ORDER BY ts DESC, id DESC LIMIT 1
                    """,
                    (conversation_id,),
                ).fetchone()
            try:
                cid = int(call_id)
            except (TypeError, ValueError):
                return None
            row = self.conn.execute(
                "SELECT * FROM request_calls WHERE id = ?", (cid,)
            ).fetchone()
            if row and row["conversation_id"] != conversation_id:
                return None
            return row

    def pick_stats_row(self, conversation_id: str) -> dict | None:
        """优先 ok+实测，否则最近一次。"""
        listed = self.list_calls(conversation_id, limit=50)
        if not listed:
            return None
        for r in listed:
            if r.get("status") == "ok" and r.get("prompt_tokens") is not None:
                return r
        return listed[0]

    def begin(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        round: int,
        model: str | None,
        model_label: str | None,
        candidate_id: str | None,
        api_messages: list[dict],
        annotations: list[dict],
        tools: list[dict] | None,
        params: dict[str, Any],
    ) -> int | None:
        try:
            return self._begin_impl(
                conversation_id=conversation_id,
                turn_id=turn_id,
                round=round,
                model=model,
                model_label=model_label,
                candidate_id=candidate_id,
                api_messages=api_messages,
                annotations=annotations,
                tools=tools,
                params=params,
            )
        except Exception:
            _log.exception("request_log.begin failed")
            with self._lock:
                self.conn.rollback()
            return None

    def _begin_impl(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        round: int,
        model: str | None,
        model_label: str | None,
        candidate_id: str | None,
        api_messages: list[dict],
        annotations: list[dict],
        tools: list[dict] | None,
        params: dict[str, Any],
    ) -> int:
        ts = _utc_now()
        tools_list = list(tools or [])
        tools_hash = _blob_hash(tools_list) if tools_list else None
        tool_count = len(tools_list)
        params_json = _canonical_json(params)
        with self._lock:
            existing = self.conn.execute(
                """
                SELECT id, attempts FROM request_calls
                WHERE conversation_id = ? AND turn_id = ? AND round = ?
                """,
                (conversation_id, turn_id, round),
            ).fetchone()
            if existing:
                call_id = int(existing["id"])
                attempts = int(existing["attempts"]) + 1
                old_hashes = {
                    r["hash"]
                    for r in self.conn.execute(
                        "SELECT hash FROM request_call_messages WHERE call_id = ?",
                        (call_id,),
                    ).fetchall()
                }
                self.conn.execute(
                    "DELETE FROM request_call_messages WHERE call_id = ?",
                    (call_id,),
                )
                self.conn.execute(
                    """
                    UPDATE request_calls SET
                      ts = ?, model = ?, model_label = ?, candidate_id = ?,
                      params_json = ?, tools_hash = ?, tool_count = ?, status = 'pending',
                      attempts = ?, prompt_tokens = NULL, completion_tokens = NULL,
                      cache_tokens = NULL, duration_ms = NULL, error = NULL
                    WHERE id = ?
                    """,
                    (
                        ts,
                        model,
                        model_label,
                        candidate_id,
                        params_json,
                        tools_hash,
                        tool_count,
                        attempts,
                        call_id,
                    ),
                )
            else:
                cur = self.conn.execute(
                    """
                    INSERT INTO request_calls(
                      conversation_id, turn_id, round, ts, model, model_label,
                      candidate_id, params_json, tools_hash, tool_count, status, attempts
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 1)
                    """,
                    (
                        conversation_id,
                        turn_id,
                        round,
                        ts,
                        model,
                        model_label,
                        candidate_id,
                        params_json,
                        tools_hash,
                        tool_count,
                    ),
                )
                call_id = int(cur.lastrowid)
                old_hashes = set()
            if tools_list and tools_hash:
                self._put_blob_bytes_unlocked(
                    tools_hash, _canonical_json(tools_list).encode("utf-8")
                )
            new_hashes: set[str] = set()
            for idx, msg in enumerate(api_messages):
                ann = annotations[idx] if idx < len(annotations) else {}
                sanitized_msg = sanitize_api_message(dict(msg))
                h = _blob_hash(sanitized_msg)
                new_hashes.add(h)
                segs = segments_for_api_message(sanitized_msg, ann)
                seg_store = segment_meta_for_store(segs)
                self._put_blob_bytes_unlocked(
                    h, _canonical_json(sanitized_msg).encode("utf-8")
                )
                self.conn.execute(
                    """
                    INSERT INTO request_call_messages(call_id, idx, hash, segments_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (call_id, idx, h, _canonical_json(seg_store)),
                )
            self._gc_blobs(old_hashes - new_hashes)
            if round == 1:
                self._enforce_retention(conversation_id)
            self._enforce_global_cap()
            self.conn.commit()
            return call_id

    def finish(
        self,
        call_id: int | None,
        *,
        status: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        cache_tokens: int | None = None,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        if call_id is None:
            return
        try:
            with self._lock:
                self.conn.execute(
                    """
                    UPDATE request_calls SET
                      status = ?, prompt_tokens = ?, completion_tokens = ?,
                      cache_tokens = ?, duration_ms = ?, error = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        prompt_tokens,
                        completion_tokens,
                        cache_tokens,
                        duration_ms,
                        error,
                        call_id,
                    ),
                )
                self.conn.commit()
        except Exception:
            _log.exception("request_log.finish failed")

    def load_message_bodies(self, call_id: int) -> list[tuple[dict, list[dict]]]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT hash, segments_json FROM request_call_messages
                WHERE call_id = ? ORDER BY idx
                """,
                (call_id,),
            ).fetchall()
            out: list[tuple[dict, list[dict]]] = []
            for row in rows:
                raw = self._get_blob_raw_unlocked(row["hash"])
                if raw is None:
                    body: dict = {}
                else:
                    body = json.loads(raw.decode("utf-8"))
                seg_meta = json.loads(row["segments_json"])
                text = message_text_content(body.get("content"))
                segments = segments_from_store_meta(text, seg_meta)
                out.append((body, segments))
            return out

    def load_tools(self, tools_hash: str | None) -> list[dict]:
        if not tools_hash:
            return []
        with self._lock:
            raw = self._get_blob_raw_unlocked(tools_hash)
        if raw is None:
            return []
        return json.loads(raw.decode("utf-8"))

    def build_raw_request(self, row: sqlite3.Row) -> dict[str, Any]:
        call_id = int(row["id"])
        bodies = self.load_message_bodies(call_id)
        messages = [b for b, _ in bodies]
        params = json.loads(row["params_json"])
        tools = self.load_tools(row["tools_hash"])
        out: dict[str, Any] = {"model": row["model"], "messages": messages}
        if tools:
            out["tools"] = tools
        out.update(params)
        return out

    def _put_blob_bytes_unlocked(self, h: str, raw: bytes) -> None:
        existing = self.conn.execute(
            "SELECT hash FROM request_blobs WHERE hash = ?", (h,)
        ).fetchone()
        if existing:
            return
        compressed = zlib.compress(raw, level=6)
        self.conn.execute(
            "INSERT INTO request_blobs(hash, body, size) VALUES (?, ?, ?)",
            (h, compressed, len(raw)),
        )

    def _get_blob_raw_unlocked(self, h: str) -> bytes | None:
        row = self.conn.execute(
            "SELECT body FROM request_blobs WHERE hash = ?", (h,)
        ).fetchone()
        if not row:
            return None
        return zlib.decompress(row["body"])

    def _gc_blobs(self, candidates: set[str]) -> None:
        if not candidates:
            return
        for h in candidates:
            if not h:
                continue
            used_msg = self.conn.execute(
                "SELECT 1 FROM request_call_messages WHERE hash = ? LIMIT 1",
                (h,),
            ).fetchone()
            used_tools = self.conn.execute(
                "SELECT 1 FROM request_calls WHERE tools_hash = ? LIMIT 1",
                (h,),
            ).fetchone()
            if not used_msg and not used_tools:
                self.conn.execute("DELETE FROM request_blobs WHERE hash = ?", (h,))

    def _enforce_retention(self, conversation_id: str) -> None:
        turns = self.conn.execute(
            """
            SELECT DISTINCT turn_id, MIN(ts) AS first_ts
            FROM request_calls WHERE conversation_id = ?
            GROUP BY turn_id ORDER BY first_ts ASC
            """,
            (conversation_id,),
        ).fetchall()
        if len(turns) <= REQUEST_LOG_TURNS_PER_CONVERSATION:
            return
        drop = len(turns) - REQUEST_LOG_TURNS_PER_CONVERSATION
        for i in range(drop):
            tid = turns[i]["turn_id"]
            self._delete_turn(conversation_id, tid)

    def _delete_turn(self, conversation_id: str, turn_id: str) -> None:
        rows = self.conn.execute(
            "SELECT id, tools_hash FROM request_calls WHERE conversation_id = ? AND turn_id = ?",
            (conversation_id, turn_id),
        ).fetchall()
        if not rows:
            return
        call_ids = [int(r["id"]) for r in rows]
        tools_hashes = {r["tools_hash"] for r in rows if r["tools_hash"]}
        placeholders = ",".join("?" * len(call_ids))
        msg_hashes = {
            r["hash"]
            for r in self.conn.execute(
                f"SELECT hash FROM request_call_messages WHERE call_id IN ({placeholders})",
                call_ids,
            ).fetchall()
        }
        self.conn.execute(
            f"DELETE FROM request_call_messages WHERE call_id IN ({placeholders})",
            call_ids,
        )
        self.conn.execute(
            "DELETE FROM request_calls WHERE conversation_id = ? AND turn_id = ?",
            (conversation_id, turn_id),
        )
        self._gc_blobs(msg_hashes | tools_hashes)

    def _enforce_global_cap(self) -> None:
        count = self.conn.execute(
            "SELECT COUNT(*) AS n FROM request_calls"
        ).fetchone()["n"]
        overflow = int(count) - REQUEST_LOG_MAX_CALLS
        if overflow <= 0:
            return
        olds = self.conn.execute(
            "SELECT id, tools_hash FROM request_calls ORDER BY ts ASC LIMIT ?",
            (overflow,),
        ).fetchall()
        for row in olds:
            cid = int(row["id"])
            msg_hashes = {
                r["hash"]
                for r in self.conn.execute(
                    "SELECT hash FROM request_call_messages WHERE call_id = ?",
                    (cid,),
                ).fetchall()
            }
            self.conn.execute(
                "DELETE FROM request_call_messages WHERE call_id = ?", (cid,)
            )
            self.conn.execute("DELETE FROM request_calls WHERE id = ?", (cid,))
            tools_set = {row["tools_hash"]} if row["tools_hash"] else set()
            self._gc_blobs(msg_hashes | tools_set)
