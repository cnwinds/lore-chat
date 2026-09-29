from __future__ import annotations

import app.sqlite_compat  # noqa: F401 — FTS5 / fts5vocab 需较新 SQLite
import json
import hashlib
import sqlite3
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from app.index.partitioned.tokenize import TOKENIZER_VERSION, index_terms
from app.time import now_iso_seconds

FAMILIES: tuple[str, ...] = ("cards",)

_MAX_PARTITION_LEN = 200


def partition_family(partition: str) -> str:
    if ":" not in partition:
        raise ValueError(f"invalid partition (no colon): {partition!r}")
    family, key = partition.split(":", 1)
    if family not in FAMILIES:
        raise ValueError(f"unknown family in partition: {partition!r}")
    if not key or key.strip() != key or any(ch.isspace() for ch in key):
        raise ValueError(f"invalid partition key: {partition!r}")
    if len(partition) > _MAX_PARTITION_LEN:
        raise ValueError(f"partition too long: {partition!r}")
    return family


def validate_meta(meta: Mapping[str, Any]) -> dict[str, str | int | float | bool]:
    out: dict[str, str | int | float | bool] = {}
    for k, v in meta.items():
        if not isinstance(k, str):
            raise ValueError("meta keys must be str")
        if not isinstance(v, (str, int, float, bool)):
            raise ValueError(f"meta value type not allowed: {k}={type(v)}")
        out[k] = v
    return out


def content_hash(text: str, meta: Mapping[str, str | int | float | bool]) -> str:
    payload = text + "\x1f" + json.dumps(meta, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def terms_for_text(text: str) -> str:
    return " ".join(index_terms(text))


class PartitionedLexical:
    """partitioned.db：清单 + 每族 FTS5；每次操作独立连接。"""

    def __init__(self, path: str | Path):
        self._path = str(path)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meta(
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS items(
                  partition TEXT NOT NULL,
                  item_id TEXT NOT NULL,
                  family TEXT NOT NULL,
                  content_hash TEXT NOT NULL,
                  text TEXT NOT NULL,
                  meta_json TEXT NOT NULL DEFAULT '{}',
                  vec_state TEXT NOT NULL DEFAULT 'pending',
                  vec_model TEXT,
                  vec_attempts INTEGER NOT NULL DEFAULT 0,
                  vec_next_try_at REAL NOT NULL DEFAULT 0,
                  updated_at TEXT NOT NULL,
                  PRIMARY KEY (partition, item_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS items_family ON items(family)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS items_vec ON items(vec_state, vec_next_try_at)"
            )
            for family in FAMILIES:
                conn.execute(
                    f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS fts_{family} USING fts5(
                      partition UNINDEXED,
                      item_id UNINDEXED,
                      terms,
                      tokenize = 'unicode61 remove_diacritics 2'
                    )
                    """
                )
                conn.execute(
                    f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS fts_{family}_vocab
                    USING fts5vocab(fts_{family}, 'row')
                    """
                )
            conn.commit()
            self._maybe_migrate_tokenizer(conn)

    def _maybe_migrate_tokenizer(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT value FROM meta WHERE key='tokenizer_version'"
        ).fetchone()
        current = int(row["value"]) if row else None
        if current == TOKENIZER_VERSION:
            return
        conn.execute("BEGIN")
        try:
            for family in FAMILIES:
                conn.execute(f"DELETE FROM fts_{family}")
                rows = conn.execute(
                    "SELECT partition, item_id, text FROM items WHERE family=?",
                    (family,),
                ).fetchall()
                for r in rows:
                    conn.execute(
                        f"INSERT INTO fts_{family}(partition, item_id, terms) VALUES (?, ?, ?)",
                        (r["partition"], r["item_id"], terms_for_text(r["text"])),
                    )
            conn.execute(
                "INSERT INTO meta(key, value) VALUES ('tokenizer_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(TOKENIZER_VERSION),),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_meta(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key=?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            conn.commit()

    def partitions(self, family: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT partition FROM items WHERE family=? ORDER BY partition",
                (family,),
            ).fetchall()
            return [r["partition"] for r in rows]

    def get_item(self, partition: str, item_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM items WHERE partition=? AND item_id=?",
                (partition, item_id),
            ).fetchone()

    def count_family(self, family: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT count(*) AS c FROM items WHERE family=?", (family,)
            ).fetchone()
            return int(row["c"])

    def vocab_docs(self, family: str, terms: list[str]) -> dict[str, int]:
        if not terms:
            return {}
        out: dict[str, int] = {}
        with self._connect() as conn:
            for i in range(0, len(terms), 500):
                batch = terms[i : i + 500]
                placeholders = ",".join("?" * len(batch))
                rows = conn.execute(
                    f"SELECT term, doc FROM fts_{family}_vocab WHERE term IN ({placeholders})",
                    batch,
                ).fetchall()
                for r in rows:
                    doc = int(r["doc"])
                    if doc > 0:
                        out[r["term"]] = doc
        return out

    def fts_search(
        self,
        family: str,
        match_expr: str,
        partitions: list[str],
        limit: int,
    ) -> list[tuple[str, str, float]]:
        if not match_expr or not partitions:
            return []
        placeholders = ",".join("?" * len(partitions))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT partition, item_id, bm25(fts_{family}) AS bm
                FROM fts_{family}
                WHERE fts_{family} MATCH ? AND partition IN ({placeholders})
                ORDER BY bm25(fts_{family})
                LIMIT ?
                """,
                [match_expr, *partitions, limit],
            ).fetchall()
        # bm25() 越小越相关；对外转为正数分
        return [
            (r["partition"], r["item_id"], -float(r["bm"]))
            for r in rows
        ]

    def fetch_items(
        self, keys: Iterable[tuple[str, str]]
    ) -> dict[tuple[str, str], sqlite3.Row]:
        keys = list(keys)
        if not keys:
            return {}
        out: dict[tuple[str, str], sqlite3.Row] = {}
        with self._connect() as conn:
            for partition, item_id in keys:
                row = conn.execute(
                    "SELECT * FROM items WHERE partition=? AND item_id=?",
                    (partition, item_id),
                ).fetchone()
                if row:
                    out[(partition, item_id)] = row
        return out

    def sync_partition_tx(
        self,
        partition: str,
        family: str,
        desired: dict[str, tuple[str, dict[str, str | int | float | bool], str]],
        *,
        delete_absent: bool,
    ) -> tuple[Any, list[tuple[str, str, str | None]]]:
        """返回 (SyncStats 字段, 待删向量 [(partition, item_id, vec_model)])。"""
        added = updated = removed = unchanged = 0
        vec_deletes: list[tuple[str, str, str | None]] = []
        now = now_iso_seconds()
        with self._connect() as conn:
            conn.execute("BEGIN")
            try:
                existing_rows = conn.execute(
                    "SELECT item_id, content_hash, vec_state, vec_model FROM items WHERE partition=?",
                    (partition,),
                ).fetchall()
                existing = {r["item_id"]: r for r in existing_rows}
                desired_ids = set(desired.keys())

                for item_id, (text, meta, h) in desired.items():
                    row = existing.get(item_id)
                    if row is None:
                        conn.execute(
                            """
                            INSERT INTO items(
                              partition, item_id, family, content_hash, text, meta_json,
                              vec_state, vec_model, vec_attempts, vec_next_try_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, 0, 0, ?)
                            """,
                            (
                                partition,
                                item_id,
                                family,
                                h,
                                text,
                                json.dumps(meta, ensure_ascii=False),
                                now,
                            ),
                        )
                        conn.execute(
                            f"INSERT INTO fts_{family}(partition, item_id, terms) VALUES (?, ?, ?)",
                            (partition, item_id, terms_for_text(text)),
                        )
                        added += 1
                    elif row["content_hash"] != h:
                        old_model = row["vec_model"]
                        if row["vec_state"] == "ok" and old_model:
                            vec_deletes.append((partition, item_id, old_model))
                        conn.execute(
                            """
                            UPDATE items SET content_hash=?, text=?, meta_json=?,
                              vec_state='pending', vec_model=NULL,
                              vec_attempts=0, vec_next_try_at=0, updated_at=?
                            WHERE partition=? AND item_id=?
                            """,
                            (
                                h,
                                text,
                                json.dumps(meta, ensure_ascii=False),
                                now,
                                partition,
                                item_id,
                            ),
                        )
                        conn.execute(
                            f"DELETE FROM fts_{family} WHERE partition=? AND item_id=?",
                            (partition, item_id),
                        )
                        conn.execute(
                            f"INSERT INTO fts_{family}(partition, item_id, terms) VALUES (?, ?, ?)",
                            (partition, item_id, terms_for_text(text)),
                        )
                        updated += 1
                    else:
                        unchanged += 1

                if delete_absent:
                    for item_id, row in existing.items():
                        if item_id not in desired_ids:
                            if row["vec_state"] == "ok" and row["vec_model"]:
                                vec_deletes.append(
                                    (partition, item_id, row["vec_model"])
                                )
                            conn.execute(
                                "DELETE FROM items WHERE partition=? AND item_id=?",
                                (partition, item_id),
                            )
                            conn.execute(
                                f"DELETE FROM fts_{family} WHERE partition=? AND item_id=?",
                                (partition, item_id),
                            )
                            removed += 1

                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return (added, updated, removed, unchanged), vec_deletes

    def delete_items_tx(
        self, partition: str, family: str, item_ids: list[str]
    ) -> tuple[int, list[tuple[str, str, str | None]]]:
        vec_deletes: list[tuple[str, str, str | None]] = []
        removed = 0
        with self._connect() as conn:
            conn.execute("BEGIN")
            try:
                for item_id in item_ids:
                    row = conn.execute(
                        "SELECT vec_state, vec_model FROM items WHERE partition=? AND item_id=?",
                        (partition, item_id),
                    ).fetchone()
                    if row is None:
                        continue
                    if row["vec_state"] == "ok" and row["vec_model"]:
                        vec_deletes.append((partition, item_id, row["vec_model"]))
                    conn.execute(
                        "DELETE FROM items WHERE partition=? AND item_id=?",
                        (partition, item_id),
                    )
                    conn.execute(
                        f"DELETE FROM fts_{family} WHERE partition=? AND item_id=?",
                        (partition, item_id),
                    )
                    removed += 1
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return removed, vec_deletes

    def drop_partition_tx(
        self, partition: str, family: str
    ) -> tuple[int, list[tuple[str, str, str | None]]]:
        vec_deletes: list[tuple[str, str, str | None]] = []
        with self._connect() as conn:
            conn.execute("BEGIN")
            try:
                rows = conn.execute(
                    "SELECT item_id, vec_state, vec_model FROM items WHERE partition=?",
                    (partition,),
                ).fetchall()
                for r in rows:
                    if r["vec_state"] == "ok" and r["vec_model"]:
                        vec_deletes.append(
                            (partition, r["item_id"], r["vec_model"])
                        )
                conn.execute(
                    "DELETE FROM items WHERE partition=?", (partition,)
                )
                conn.execute(
                    f"DELETE FROM fts_{family} WHERE partition=?", (partition,)
                )
                removed = len(rows)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return removed, vec_deletes

    def select_embed_pending(
        self, limit: int, active_model: str | None
    ) -> list[sqlite3.Row]:
        now = time.time()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT partition, item_id, content_hash, family, text, vec_model
                FROM items
                WHERE vec_state='pending' AND vec_next_try_at <= ?
                ORDER BY updated_at
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()
            out = list(rows)
            remaining = limit - len(out)
            if remaining > 0 and active_model:
                extra = conn.execute(
                    """
                    SELECT partition, item_id, content_hash, family, text, vec_model
                    FROM items
                    WHERE vec_state='ok' AND vec_model IS NOT NULL AND vec_model != ?
                    ORDER BY updated_at
                    LIMIT ?
                    """,
                    (active_model, remaining),
                ).fetchall()
                out.extend(extra)
            return out

    def has_ok_items(self) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM items WHERE vec_state='ok' LIMIT 1"
            ).fetchone()
            return row is not None

    def mark_embed_failed(self, keys: list[tuple[str, str]], attempts_delta: int) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN")
            try:
                for partition, item_id in keys:
                    row = conn.execute(
                        "SELECT vec_attempts FROM items WHERE partition=? AND item_id=?",
                        (partition, item_id),
                    ).fetchone()
                    if row is None:
                        continue
                    attempts = int(row["vec_attempts"]) + attempts_delta
                    backoff = min(6 * 3600, 60 * (2 ** min(attempts, 10)))
                    conn.execute(
                        """
                        UPDATE items SET vec_attempts=?, vec_next_try_at=?
                        WHERE partition=? AND item_id=?
                        """,
                        (attempts, now + backoff, partition, item_id),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def mark_embed_ok(
        self,
        partition: str,
        item_id: str,
        *,
        content_hash: str,
        model: str,
    ) -> bool:
        """哈希仍匹配才更新；返回是否写入。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT content_hash FROM items WHERE partition=? AND item_id=?",
                (partition, item_id),
            ).fetchone()
            if row is None or row["content_hash"] != content_hash:
                return False
            conn.execute(
                """
                UPDATE items SET vec_state='ok', vec_model=?, vec_attempts=0, vec_next_try_at=0
                WHERE partition=? AND item_id=?
                """,
                (model, partition, item_id),
            )
            conn.commit()
            return True

    def count_by_vec_model(self, family: str, model: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT count(*) AS c FROM items WHERE family=? AND vec_model=?",
                (family, model),
            ).fetchone()
            return int(row["c"])

    def on_embedder_changed(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE items SET vec_attempts=0, vec_next_try_at=0
                WHERE vec_state='pending'
                """
            )
            conn.commit()

    def force_tokenizer_version(self, version: int) -> None:
        # 仅测试用：手工改 meta.tokenizer_version 以触发 FTS 全量重建。
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES ('tokenizer_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(version),),
            )
            conn.commit()
        self._ensure_schema()
