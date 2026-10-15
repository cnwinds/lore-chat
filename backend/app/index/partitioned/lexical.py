from __future__ import annotations

import app.sqlite_compat  # noqa: F401 — FTS5 / fts5vocab 需较新 SQLite
import json
import hashlib
import re
import sqlite3
import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from app.closing import close_quietly
from app.index.partitioned import vectors
from app.index.partitioned.tokenize import TOKENIZER_VERSION, index_terms
from app.time import now_iso_seconds

FAMILIES: tuple[str, ...] = ("cards", "kb", "conv")

_MAX_PARTITION_LEN = 200
_GRP_PREFIX_UPPER_SUFFIX = chr(0x10FFFF)
_META_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


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
        if k in ("partition", "item_id"):
            raise ValueError(f"reserved meta key: {k}")
        if not isinstance(v, (str, int, float, bool)):
            raise ValueError(f"meta value type not allowed: {k}={type(v)}")
        out[k] = v
    return out


def content_hash(text: str, meta: Mapping[str, str | int | float | bool]) -> str:
    payload = text + "\x1f" + json.dumps(meta, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def terms_for_text(text: str) -> str:
    return " ".join(index_terms(text))


def _sql_bind_value(value: str | int | float | bool) -> str | int | float:
    # json_extract 返回 SQL 标量；bool 在 JSON 里是 true/false，提取结果为 1/0。
    if isinstance(value, bool):
        return 1 if value else 0
    return value


class PartitionedLexical:
    """partitioned.db：清单 + 每族 FTS5；每线程复用一条连接，close() 后退回每次独立连接。"""

    def __init__(self, path: str | Path):
        self._path = str(path)
        self._local = threading.local()
        self._conns_lock = threading.Lock()
        self._conns: dict[threading.Thread, sqlite3.Connection] = {}
        self._closed = False
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=5, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _connect(self) -> sqlite3.Connection:
        # 调用方只用 `with conn:` 收尾事务、不关闭连接，同一线程内不得嵌套。
        if self._closed:
            return self._open()
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            return conn
        conn = self._open()
        with self._conns_lock:
            if self._closed:
                return conn
            for thread in [t for t in self._conns if not t.is_alive()]:
                close_quietly(self._conns.pop(thread))
            self._conns[threading.current_thread()] = conn
        self._local.conn = conn
        return conn

    def close(self) -> None:
        with self._conns_lock:
            self._closed = True
            conns = list(self._conns.values())
            self._conns.clear()
        for conn in conns:
            close_quietly(conn)

    def _ensure_grp_column(self, conn: sqlite3.Connection) -> None:
        cols = {
            row[1] for row in conn.execute("PRAGMA table_info(items)").fetchall()
        }
        if "grp" not in cols:
            conn.execute(
                "ALTER TABLE items ADD COLUMN grp TEXT NOT NULL DEFAULT ''"
            )

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
                  grp TEXT NOT NULL DEFAULT '',
                  PRIMARY KEY (partition, item_id)
                )
                """
            )
            self._ensure_grp_column(conn)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS items_family ON items(family)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS items_vec ON items(vec_state, vec_next_try_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS items_grp ON items(partition, grp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS items_pending ON items(vec_state, vec_next_try_at, updated_at)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vectors(
                  partition TEXT NOT NULL,
                  item_id TEXT NOT NULL,
                  family TEXT NOT NULL,
                  model TEXT NOT NULL,
                  vec BLOB NOT NULL,
                  PRIMARY KEY (partition, item_id)
                )
                """
            )
            # 向量曾存在 Chroma；没有对应向量行的「已嵌入」条目交后台重嵌。
            conn.execute(
                """
                UPDATE items
                SET vec_state='pending', vec_model=NULL, vec_attempts=0, vec_next_try_at=0
                WHERE vec_state='ok' AND NOT EXISTS (
                  SELECT 1 FROM vectors v
                  WHERE v.partition = items.partition
                    AND v.item_id = items.item_id
                    AND v.model = items.vec_model
                )
                """
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

    def groups(self, partition: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT grp FROM items
                WHERE partition=? AND grp != ''
                ORDER BY grp
                """,
                (partition,),
            ).fetchall()
            return [r["grp"] for r in rows]

    def group_items(self, partition: str, group: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT * FROM items
                WHERE partition=? AND grp=?
                ORDER BY item_id
                """,
                (partition, group),
            ).fetchall()

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

    @staticmethod
    def _filter_sql_clauses(
        filters: Sequence[Any],
    ) -> tuple[str, list[Any]]:
        """返回 JOIN items 后的 AND 片段与绑定参数（不含 WHERE 前缀）。"""
        if not filters:
            return "", []
        parts: list[str] = []
        params: list[Any] = []
        for flt in filters:
            key = flt.key
            if not _META_KEY_RE.match(key):
                raise ValueError(f"invalid meta filter key: {key!r}")
            path = f"$.{key}"
            if flt.op == "in":
                if not isinstance(flt.value, tuple) or not flt.value:
                    raise ValueError("in filter requires non-empty tuple value")
                placeholders = ",".join("?" * len(flt.value))
                parts.append(
                    f"json_extract(i.meta_json, '{path}') IN ({placeholders})"
                )
                params.extend(_sql_bind_value(x) for x in flt.value)
                continue
            val = _sql_bind_value(flt.value)
            if flt.op == "eq":
                parts.append(f"json_extract(i.meta_json, '{path}') = ?")
                params.append(val)
            elif flt.op == "ne":
                parts.append(f"json_extract(i.meta_json, '{path}') IS NOT ?")
                params.append(val)
            elif flt.op == "gte":
                parts.append(f"json_extract(i.meta_json, '{path}') >= ?")
                params.append(val)
            elif flt.op == "lt":
                parts.append(f"json_extract(i.meta_json, '{path}') < ?")
                params.append(val)
            else:
                raise ValueError(f"invalid meta filter op: {flt.op!r}")
        return " AND " + " AND ".join(parts), params

    @staticmethod
    def _group_prefix_sql_clauses(
        prefixes: Sequence[str],
    ) -> tuple[str, list[Any]]:
        if not prefixes:
            return "", []
        parts: list[str] = []
        params: list[Any] = []
        for prefix in prefixes:
            if not prefix:
                raise ValueError("group prefix must not be empty")
            upper = prefix + _GRP_PREFIX_UPPER_SUFFIX
            parts.append("(i.grp >= ? AND i.grp < ?)")
            params.extend([prefix, upper])
        return " AND (" + " OR ".join(parts) + ")", params

    def fts_search(
        self,
        family: str,
        match_expr: str,
        partitions: list[str],
        limit: int,
        filters: Sequence[Any] = (),
        *,
        group_prefixes: Sequence[str] | None = None,
    ) -> list[tuple[str, str, float]]:
        if not match_expr or not partitions:
            return []
        placeholders = ",".join("?" * len(partitions))
        filter_sql, filter_params = self._filter_sql_clauses(filters)
        grp_sql, grp_params = self._group_prefix_sql_clauses(group_prefixes or ())
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT f.partition, f.item_id, bm25(fts_{family}) AS bm
                FROM fts_{family} f
                JOIN items i ON i.partition = f.partition AND i.item_id = f.item_id
                WHERE fts_{family} MATCH ? AND f.partition IN ({placeholders})
                {filter_sql}{grp_sql}
                ORDER BY bm25(fts_{family})
                LIMIT ?
                """,
                [match_expr, *partitions, *filter_params, *grp_params, limit],
            ).fetchall()
        return [
            (r["partition"], r["item_id"], -float(r["bm"]))
            for r in rows
        ]

    def vector_top_k(
        self,
        family: str,
        model: str,
        query: Sequence[float],
        partitions: list[str],
        k: int,
        filters: Sequence[Any] = (),
        *,
        group_prefixes: Sequence[str] | None = None,
        batch_size: int = 512,
    ) -> list[tuple[str, str, float]]:
        if not partitions or k <= 0:
            return []
        placeholders = ",".join("?" * len(partitions))
        filter_sql, filter_params = self._filter_sql_clauses(filters)
        grp_sql, grp_params = self._group_prefix_sql_clauses(group_prefixes or ())
        with self._connect() as conn:
            cur = conn.execute(
                f"""
                SELECT v.partition, v.item_id, v.vec
                FROM vectors v
                JOIN items i ON i.partition = v.partition AND i.item_id = v.item_id
                WHERE v.family=? AND v.model=? AND v.partition IN ({placeholders})
                  AND i.vec_state='ok'
                {filter_sql}{grp_sql}
                """,
                [family, model, *partitions, *filter_params, *grp_params],
            )
            try:
                batches = iter(lambda: cur.fetchmany(batch_size), [])
                return vectors.top_k(batches, query, k)
            finally:
                cur.close()

    def like_search(
        self,
        family: str,
        pattern: str,
        partitions: list[str],
        limit: int,
        filters: Sequence[Any],
        *,
        group_prefixes: Sequence[str] | None = None,
    ) -> list[tuple[str, str, float]]:
        if not pattern or not partitions:
            return []
        placeholders = ",".join("?" * len(partitions))
        filter_sql, filter_params = self._filter_sql_clauses(filters)
        grp_sql, grp_params = self._group_prefix_sql_clauses(group_prefixes or ())
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT i.partition, i.item_id
                FROM items i
                WHERE i.family=? AND i.partition IN ({placeholders})
                  AND i.text LIKE ? ESCAPE '\\'
                {filter_sql}{grp_sql}
                LIMIT ?
                """,
                [family, *partitions, pattern, *filter_params, *grp_params, limit],
            ).fetchall()
        return [(r["partition"], r["item_id"], 0.0) for r in rows]

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

    def _apply_desired_item(
        self,
        conn: sqlite3.Connection,
        *,
        partition: str,
        family: str,
        item_id: str,
        group: str,
        text: str,
        meta: dict[str, str | int | float | bool],
        h: str,
        row: sqlite3.Row | None,
        now: str,
    ) -> str:
        """返回 added | updated | unchanged | moved。"""
        if row is None:
            conn.execute(
                """
                INSERT INTO items(
                  partition, item_id, family, content_hash, text, meta_json,
                  vec_state, vec_model, vec_attempts, vec_next_try_at, updated_at, grp
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, 0, 0, ?, ?)
                """,
                (
                    partition,
                    item_id,
                    family,
                    h,
                    text,
                    json.dumps(meta, ensure_ascii=False),
                    now,
                    group,
                ),
            )
            conn.execute(
                f"INSERT INTO fts_{family}(partition, item_id, terms) VALUES (?, ?, ?)",
                (partition, item_id, terms_for_text(text)),
            )
            return "added"

        moved = row["grp"] != group
        if row["content_hash"] == h and not moved:
            return "unchanged"

        if row["content_hash"] == h and moved:
            conn.execute(
                "UPDATE items SET grp=?, updated_at=? WHERE partition=? AND item_id=?",
                (group, now, partition, item_id),
            )
            return "unchanged"

        conn.execute(
            "DELETE FROM vectors WHERE partition=? AND item_id=?",
            (partition, item_id),
        )
        conn.execute(
            """
            UPDATE items SET content_hash=?, text=?, meta_json=?, grp=?,
              vec_state='pending', vec_model=NULL,
              vec_attempts=0, vec_next_try_at=0, updated_at=?
            WHERE partition=? AND item_id=?
            """,
            (
                h,
                text,
                json.dumps(meta, ensure_ascii=False),
                group,
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
        return "updated"

    def sync_partition_tx(
        self,
        partition: str,
        family: str,
        desired: dict[str, tuple[str, dict[str, str | int | float | bool], str]],
        *,
        delete_absent: bool,
    ) -> tuple[int, int, int, int]:
        return self._sync_scope_tx(
            partition,
            family,
            desired,
            group="",
            scope="partition",
            delete_absent=delete_absent,
        )

    def sync_group_tx(
        self,
        partition: str,
        family: str,
        group: str,
        desired: dict[str, tuple[str, dict[str, str | int | float | bool], str]],
        *,
        delete_absent: bool = True,
    ) -> tuple[int, int, int, int]:
        return self._sync_scope_tx(
            partition,
            family,
            desired,
            group=group,
            scope="group",
            delete_absent=delete_absent,
        )

    @staticmethod
    def _delete_item(
        conn: sqlite3.Connection, partition: str, family: str, item_id: str
    ) -> None:
        conn.execute(
            "DELETE FROM items WHERE partition=? AND item_id=?",
            (partition, item_id),
        )
        conn.execute(
            f"DELETE FROM fts_{family} WHERE partition=? AND item_id=?",
            (partition, item_id),
        )
        conn.execute(
            "DELETE FROM vectors WHERE partition=? AND item_id=?",
            (partition, item_id),
        )

    def _sync_scope_tx(
        self,
        partition: str,
        family: str,
        desired: dict[str, tuple[str, dict[str, str | int | float | bool], str]],
        *,
        group: str,
        scope: str,
        delete_absent: bool,
    ) -> tuple[int, int, int, int]:
        added = updated = removed = unchanged = 0
        now = now_iso_seconds()
        with self._connect() as conn:
            conn.execute("BEGIN")
            try:
                if scope == "partition":
                    existing_rows = conn.execute(
                        "SELECT * FROM items WHERE partition=?",
                        (partition,),
                    ).fetchall()
                else:
                    existing_rows = conn.execute(
                        "SELECT * FROM items WHERE partition=? AND grp=?",
                        (partition, group),
                    ).fetchall()
                existing_in_scope = {r["item_id"]: r for r in existing_rows}
                all_partition = dict(existing_in_scope)
                if scope != "partition":
                    desired_ids_list = list(desired.keys())
                    for i in range(0, len(desired_ids_list), 500):
                        batch_ids = desired_ids_list[i : i + 500]
                        placeholders = ",".join("?" * len(batch_ids))
                        rows = conn.execute(
                            f"""
                            SELECT * FROM items
                            WHERE partition=? AND item_id IN ({placeholders})
                            """,
                            (partition, *batch_ids),
                        ).fetchall()
                        for r in rows:
                            all_partition[r["item_id"]] = r
                desired_ids = set(desired.keys())

                for item_id, (text, meta, h) in desired.items():
                    row = all_partition.get(item_id)
                    outcome = self._apply_desired_item(
                        conn,
                        partition=partition,
                        family=family,
                        item_id=item_id,
                        group=group,
                        text=text,
                        meta=meta,
                        h=h,
                        row=row,
                        now=now,
                    )
                    if outcome == "added":
                        added += 1
                        all_partition[item_id] = conn.execute(
                            "SELECT * FROM items WHERE partition=? AND item_id=?",
                            (partition, item_id),
                        ).fetchone()
                    elif outcome == "updated":
                        updated += 1
                    else:
                        unchanged += 1

                if delete_absent:
                    for item_id in existing_in_scope:
                        if item_id not in desired_ids:
                            self._delete_item(conn, partition, family, item_id)
                            removed += 1

                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return added, updated, removed, unchanged

    def _delete_where_tx(
        self, family: str, where: str, params: tuple[Any, ...]
    ) -> int:
        with self._connect() as conn:
            conn.execute("BEGIN")
            try:
                rows = conn.execute(
                    f"SELECT partition, item_id FROM items WHERE {where}", params
                ).fetchall()
                for r in rows:
                    self._delete_item(conn, r["partition"], family, r["item_id"])
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return len(rows)

    def drop_group_tx(self, partition: str, family: str, group: str) -> int:
        return self._delete_where_tx(
            family, "partition=? AND grp=?", (partition, group)
        )

    def drop_groups_tx(self, partition: str, family: str, prefix: str) -> int:
        upper = prefix + _GRP_PREFIX_UPPER_SUFFIX
        return self._delete_where_tx(
            family,
            "partition=? AND grp >= ? AND grp < ?",
            (partition, prefix, upper),
        )

    def delete_items_tx(
        self, partition: str, family: str, item_ids: list[str]
    ) -> int:
        removed = 0
        with self._connect() as conn:
            conn.execute("BEGIN")
            try:
                for item_id in item_ids:
                    row = conn.execute(
                        "SELECT 1 FROM items WHERE partition=? AND item_id=?",
                        (partition, item_id),
                    ).fetchone()
                    if row is None:
                        continue
                    self._delete_item(conn, partition, family, item_id)
                    removed += 1
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return removed

    def drop_partition_tx(self, partition: str, family: str) -> int:
        return self._delete_where_tx(family, "partition=?", (partition,))

    def select_embed_pending(
        self,
        limit: int,
        active_model: str | None,
        *,
        exclude_families: frozenset[str] = frozenset(),
    ) -> list[sqlite3.Row]:
        now = time.time()
        fam_clause = ""
        fam_params: list[Any] = []
        if exclude_families:
            placeholders = ",".join("?" * len(exclude_families))
            fam_clause = f" AND family NOT IN ({placeholders})"
            fam_params = list(exclude_families)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT partition, item_id, content_hash, family, text, vec_model, meta_json
                FROM items
                WHERE vec_state='pending' AND vec_next_try_at <= ?
                {fam_clause}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (now, *fam_params, limit),
            ).fetchall()
            out = list(rows)
            remaining = limit - len(out)
            if remaining > 0 and active_model:
                extra = conn.execute(
                    f"""
                    SELECT partition, item_id, content_hash, family, text, vec_model, meta_json
                    FROM items
                    WHERE vec_state='ok' AND vec_next_try_at <= ?
                      AND vec_model IS NOT NULL AND vec_model != ?
                    {fam_clause}
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (now, active_model, *fam_params, remaining),
                ).fetchall()
                out.extend(extra)
            return out

    def has_stale_vectors(self, active_model: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM items
                WHERE vec_state='ok' AND vec_model IS NOT NULL AND vec_model != ?
                LIMIT 1
                """,
                (active_model,),
            ).fetchone()
            return row is not None

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

    def store_embeddings(
        self, entries: Sequence[tuple[str, str, str, str, bytes]]
    ) -> list[tuple[str, str]]:
        """(partition, item_id, content_hash, model, vec)；哈希仍匹配才写，返回写入的键。"""
        written: list[tuple[str, str]] = []
        if not entries:
            return written
        with self._connect() as conn:
            conn.execute("BEGIN")
            try:
                for partition, item_id, h, model, vec in entries:
                    row = conn.execute(
                        "SELECT family, content_hash FROM items WHERE partition=? AND item_id=?",
                        (partition, item_id),
                    ).fetchone()
                    if row is None or row["content_hash"] != h:
                        continue
                    conn.execute(
                        """
                        INSERT INTO vectors(partition, item_id, family, model, vec)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(partition, item_id) DO UPDATE SET
                          family=excluded.family, model=excluded.model, vec=excluded.vec
                        """,
                        (partition, item_id, row["family"], model, vec),
                    )
                    conn.execute(
                        """
                        UPDATE items SET vec_state='ok', vec_model=?, vec_attempts=0, vec_next_try_at=0
                        WHERE partition=? AND item_id=?
                        """,
                        (model, partition, item_id),
                    )
                    written.append((partition, item_id))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return written

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
