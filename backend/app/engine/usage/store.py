"""LLM 用量持久化：独立 usage.db。"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS usage_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_prices (
    model TEXT PRIMARY KEY,
    prompt_per_1k REAL,
    completion_per_1k REAL,
    embed_per_1k REAL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_events (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    model TEXT NOT NULL,
    kind TEXT NOT NULL,
    role TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    tokens_known INTEGER NOT NULL DEFAULT 0,
    prompt_price_per_1k REAL,
    completion_price_per_1k REAL,
    embed_price_per_1k REAL,
    cost REAL,
    status TEXT NOT NULL,
    error TEXT,
    duration_ms INTEGER,
    conversation_id TEXT,
    turn_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_usage_events_ts ON usage_events(ts);
CREATE INDEX IF NOT EXISTS idx_usage_events_model ON usage_events(model);
"""

_DEFAULT_TZ = "Asia/Shanghai"
_DEFAULT_RETENTION_DAYS = "365"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UsageStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(_SCHEMA)
            self.conn.commit()
            self._ensure_meta("timezone", _DEFAULT_TZ)
            self._ensure_meta("retention_days", _DEFAULT_RETENTION_DAYS)

    def close(self) -> None:
        with self._lock:
            if self.conn is not None:
                self.conn.close()
                self.conn = None

    def _ensure_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO usage_meta(key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()

    def get_meta(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self.conn.execute(
                "SELECT value FROM usage_meta WHERE key = ?", (key,)
            ).fetchone()
        return str(row["value"]) if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO usage_meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self.conn.commit()

    def prefs(self) -> dict[str, Any]:
        return {
            "timezone": self.get_meta("timezone", _DEFAULT_TZ),
            "retention_days": int(
                self.get_meta("retention_days", _DEFAULT_RETENTION_DAYS) or "365"
            ),
        }

    def update_prefs(self, *, timezone_name: str | None = None, retention_days: int | None = None) -> dict[str, Any]:
        if timezone_name is not None:
            # validate
            ZoneInfo(timezone_name)
            self.set_meta("timezone", timezone_name)
        if retention_days is not None:
            if retention_days < 1:
                raise ValueError("retention_days must be >= 1")
            self.set_meta("retention_days", str(int(retention_days)))
        return self.prefs()

    def get_price(self, model: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM model_prices WHERE model = ?", (model,)
            ).fetchone()
        return dict(row) if row else None

    def list_prices(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM model_prices ORDER BY model"
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_price(
        self,
        model: str,
        *,
        prompt_per_1k: float | None = None,
        completion_per_1k: float | None = None,
        embed_per_1k: float | None = None,
    ) -> dict[str, Any]:
        model = (model or "").strip()
        if not model:
            raise ValueError("model required")
        now = _utc_now()
        with self._lock:
            existing = self.conn.execute(
                "SELECT * FROM model_prices WHERE model = ?", (model,)
            ).fetchone()
            if existing:
                p = existing["prompt_per_1k"] if prompt_per_1k is None else prompt_per_1k
                c = (
                    existing["completion_per_1k"]
                    if completion_per_1k is None
                    else completion_per_1k
                )
                e = existing["embed_per_1k"] if embed_per_1k is None else embed_per_1k
                self.conn.execute(
                    "UPDATE model_prices SET prompt_per_1k=?, completion_per_1k=?, "
                    "embed_per_1k=?, updated_at=? WHERE model=?",
                    (p, c, e, now, model),
                )
            else:
                self.conn.execute(
                    "INSERT INTO model_prices(model, prompt_per_1k, completion_per_1k, "
                    "embed_per_1k, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (model, prompt_per_1k, completion_per_1k, embed_per_1k, now),
                )
            self.conn.commit()
            row = self.conn.execute(
                "SELECT * FROM model_prices WHERE model = ?", (model,)
            ).fetchone()
        return dict(row)

    def ensure_model_price_row(self, model: str) -> None:
        model = (model or "").strip()
        if not model:
            return
        with self._lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO model_prices(model, prompt_per_1k, completion_per_1k, "
                "embed_per_1k, updated_at) VALUES (?, NULL, NULL, NULL, ?)",
                (model, _utc_now()),
            )
            self.conn.commit()

    def insert_event(self, event: dict[str, Any]) -> str:
        eid = event.get("id") or uuid.uuid4().hex
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO usage_events(
                    id, ts, model, kind, role,
                    prompt_tokens, completion_tokens, total_tokens, tokens_known,
                    prompt_price_per_1k, completion_price_per_1k, embed_price_per_1k, cost,
                    status, error, duration_ms, conversation_id, turn_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eid,
                    event.get("ts") or _utc_now(),
                    event["model"],
                    event["kind"],
                    event.get("role"),
                    event.get("prompt_tokens"),
                    event.get("completion_tokens"),
                    event.get("total_tokens"),
                    1 if event.get("tokens_known") else 0,
                    event.get("prompt_price_per_1k"),
                    event.get("completion_price_per_1k"),
                    event.get("embed_price_per_1k"),
                    event.get("cost"),
                    event.get("status") or "ok",
                    event.get("error"),
                    event.get("duration_ms"),
                    event.get("conversation_id"),
                    event.get("turn_id"),
                ),
            )
            self.conn.commit()
        self.ensure_model_price_row(event["model"])
        return eid

    def clear_all(self) -> int:
        with self._lock:
            cur = self.conn.execute("DELETE FROM usage_events")
            self.conn.commit()
            return cur.rowcount

    def prune(self, *, retention_days: int | None = None) -> int:
        days = retention_days
        if days is None:
            days = int(self.get_meta("retention_days", _DEFAULT_RETENTION_DAYS))
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
        ).isoformat()
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM usage_events WHERE ts < ?", (cutoff,)
            )
            self.conn.commit()
            return cur.rowcount

    def list_events(
        self,
        *,
        start: str | None = None,
        end: str | None = None,
        model: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        args: list[Any] = []
        if start:
            clauses.append("ts >= ?")
            args.append(start)
        if end:
            clauses.append("ts < ?")
            args.append(end)
        if model:
            clauses.append("model = ?")
            args.append(model)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            f"SELECT * FROM usage_events{where} ORDER BY ts DESC LIMIT ? OFFSET ?"
        )
        args.extend([max(1, min(int(limit), 500)), max(0, int(offset))])
        with self._lock:
            rows = self.conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def summarize(
        self,
        *,
        granularity: str,
        start: str,
        end: str,
        timezone_name: str | None = None,
    ) -> dict[str, Any]:
        """按桶 + 模型聚合。start/end 为 UTC ISO。"""
        tz_name = timezone_name or self.get_meta("timezone", _DEFAULT_TZ)
        tz = ZoneInfo(tz_name)
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM usage_events WHERE ts >= ? AND ts < ? ORDER BY ts",
                (start, end),
            ).fetchall()

        buckets: dict[str, dict[str, Any]] = {}
        by_model: dict[str, dict[str, Any]] = {}
        totals = _empty_agg()

        for row in rows:
            local = _parse_ts(row["ts"]).astimezone(tz)
            key = _bucket_key(local, granularity)
            b = buckets.setdefault(key, _empty_agg())
            _accumulate(b, row)
            m = by_model.setdefault(row["model"], _empty_agg())
            m["model"] = row["model"]
            _accumulate(m, row)
            _accumulate(totals, row)

        bucket_list = [{"bucket": k, **v} for k, v in sorted(buckets.items())]
        model_list = sorted(by_model.values(), key=lambda x: x["model"])
        return {
            "timezone": tz_name,
            "granularity": granularity,
            "start": start,
            "end": end,
            "totals": totals,
            "by_bucket": bucket_list,
            "by_model": model_list,
        }


def _empty_agg() -> dict[str, Any]:
    return {
        "calls": 0,
        "ok_calls": 0,
        "error_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "unknown_token_calls": 0,
        "cost": 0.0,
        "cost_known_calls": 0,
        "unpriced_calls": 0,
    }


def _accumulate(agg: dict[str, Any], row: sqlite3.Row | dict) -> None:
    agg["calls"] += 1
    status = row["status"] if not isinstance(row, dict) else row.get("status")
    if status == "ok":
        agg["ok_calls"] += 1
    else:
        agg["error_calls"] += 1
    tokens_known = row["tokens_known"] if not isinstance(row, dict) else row.get("tokens_known")
    if tokens_known:
        agg["prompt_tokens"] += int(row["prompt_tokens"] or 0)
        agg["completion_tokens"] += int(row["completion_tokens"] or 0)
        agg["total_tokens"] += int(row["total_tokens"] or 0)
    else:
        agg["unknown_token_calls"] += 1
    cost = row["cost"] if not isinstance(row, dict) else row.get("cost")
    if cost is not None:
        agg["cost"] += float(cost)
        agg["cost_known_calls"] += 1
    elif tokens_known:
        agg["unpriced_calls"] += 1


def _parse_ts(ts: str) -> datetime:
    raw = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _bucket_key(local: datetime, granularity: str) -> str:
    g = (granularity or "day").lower()
    if g == "hour":
        return local.strftime("%Y-%m-%d %H:00")
    if g == "day":
        return local.strftime("%Y-%m-%d")
    if g == "week":
        # ISO week: Monday start
        iso = local.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if g == "month":
        return local.strftime("%Y-%m")
    raise ValueError(f"unsupported granularity: {granularity}")
