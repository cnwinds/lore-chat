"""后台 LLM 调用快照（独立于主对话 request_log）。"""

from __future__ import annotations

import json
import sqlite3
import threading
import zlib
from datetime import datetime, timezone
from typing import Any

from app.engine.usage.request_segment import message_text_content, sanitize_api_message
from app.logging_config import get_logger

_log = get_logger("background_call_log")

_MAX_PER_PURPOSE = 30
_RESPONSE_MAX_CHARS = 16000

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS background_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  purpose TEXT NOT NULL,
  variant TEXT,
  ts TEXT NOT NULL,
  model TEXT,
  model_label TEXT,
  candidate_id TEXT,
  chain TEXT,
  status TEXT NOT NULL,
  error TEXT,
  duration_ms INTEGER,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  conversation_id TEXT,
  scope TEXT,
  params_json TEXT NOT NULL DEFAULT '{}',
  messages_blob BLOB NOT NULL,
  response TEXT,
  response_truncated INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_bg_calls_purpose_ts ON background_calls(purpose, ts DESC);
CREATE INDEX IF NOT EXISTS idx_bg_calls_cid ON background_calls(conversation_id);
CREATE INDEX IF NOT EXISTS idx_bg_calls_scope ON background_calls(scope);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _flatten_messages(messages: list[dict]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in messages:
        role = str(m.get("role") or "")
        content = message_text_content(m.get("content"))
        out.append({"role": role, "content": content})
    return out


class BackgroundCallLog:
    def __init__(self, db_path):
        from pathlib import Path

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(_SCHEMA)
            self.conn.commit()

    def close(self) -> None:
        with self._lock:
            if self.conn is not None:
                self.conn.close()
                self.conn = None

    def record(
        self,
        *,
        purpose: str,
        variant: str | None,
        model: str | None,
        model_label: str | None,
        candidate_id: str | None,
        chain: str | None,
        temperature: float | None,
        api_messages: list[dict],
        response: str | None,
        status: str,
        error: str | None,
        duration_ms: int | None,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        conversation_id: str | None,
        scope: str | None,
    ) -> None:
        try:
            sanitized = [sanitize_api_message(dict(m)) for m in api_messages]
            flat = _flatten_messages(sanitized)
            blob = zlib.compress(
                json.dumps(flat, ensure_ascii=False).encode("utf-8"), level=6
            )
            resp = response or ""
            truncated = False
            if len(resp) > _RESPONSE_MAX_CHARS:
                resp = resp[:_RESPONSE_MAX_CHARS]
                truncated = True
            params = {}
            if temperature is not None:
                params["temperature"] = temperature
            with self._lock:
                self.conn.execute(
                    """
                    INSERT INTO background_calls(
                        purpose, variant, ts, model, model_label, candidate_id, chain,
                        status, error, duration_ms, prompt_tokens, completion_tokens,
                        conversation_id, scope, params_json, messages_blob, response,
                        response_truncated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        purpose,
                        variant,
                        _utc_now(),
                        model,
                        model_label,
                        candidate_id,
                        chain,
                        status,
                        error,
                        duration_ms,
                        prompt_tokens,
                        completion_tokens,
                        conversation_id,
                        scope,
                        json.dumps(params, ensure_ascii=False),
                        blob,
                        resp or None,
                        1 if truncated else 0,
                    ),
                )
                self.conn.execute(
                    """
                    DELETE FROM background_calls WHERE id IN (
                        SELECT id FROM background_calls
                        WHERE purpose = ?
                        ORDER BY ts DESC, id DESC
                        LIMIT -1 OFFSET ?
                    )
                    """,
                    (purpose, _MAX_PER_PURPOSE),
                )
                self.conn.commit()
        except Exception:
            _log.exception("background call record failed purpose=%s", purpose)

    def list_calls(self, purpose: str, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(100, int(limit)))
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT id, purpose, variant, ts, model, model_label, chain, status,
                       duration_ms, prompt_tokens, completion_tokens,
                       conversation_id, scope, error
                FROM background_calls
                WHERE purpose = ?
                ORDER BY ts DESC, id DESC
                LIMIT ?
                """,
                (purpose, limit),
            ).fetchall()
        return [_summary_row(r) for r in rows]

    def get_call(self, call_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM background_calls WHERE id = ?", (call_id,)
            ).fetchone()
        if row is None:
            return None
        summary = _summary_row(row)
        try:
            flat = json.loads(zlib.decompress(row["messages_blob"]).decode("utf-8"))
        except Exception:
            flat = []
        params = {}
        try:
            params = json.loads(row["params_json"] or "{}")
        except json.JSONDecodeError:
            params = {}
        summary["params"] = params
        summary["messages"] = flat
        summary["response"] = row["response"]
        summary["response_truncated"] = bool(row["response_truncated"])
        return summary

    def delete_conversation(self, cid: str) -> None:
        if not cid:
            return
        try:
            with self._lock:
                self.conn.execute(
                    "DELETE FROM background_calls WHERE conversation_id = ?", (cid,)
                )
                self.conn.commit()
        except Exception:
            _log.exception("background call delete_conversation failed cid=%s", cid)

    def delete_scope(self, scope: str) -> None:
        if not scope:
            return
        try:
            with self._lock:
                self.conn.execute(
                    "DELETE FROM background_calls WHERE scope = ?", (scope,)
                )
                self.conn.commit()
        except Exception:
            _log.exception("background call delete_scope failed scope=%s", scope)


def _summary_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "purpose": row["purpose"],
        "variant": row["variant"],
        "ts": row["ts"],
        "model": row["model"],
        "model_label": row["model_label"],
        "chain": row["chain"],
        "status": row["status"],
        "duration_ms": row["duration_ms"],
        "prompt_tokens": row["prompt_tokens"],
        "completion_tokens": row["completion_tokens"],
        "conversation_id": row["conversation_id"],
        "scope": row["scope"],
        "error": row["error"],
    }
