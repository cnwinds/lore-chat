from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.engine.memory.constants import ORIGIN_RANK

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS memory_facts (
    id TEXT PRIMARY KEY,
    owner_key TEXT NOT NULL,
    slot_key TEXT NOT NULL,
    category TEXT NOT NULL,
    statement TEXT NOT NULL,
    normalized_value_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    origin TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    sensitivity TEXT NOT NULL DEFAULT 'normal',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    confirmed_at TEXT,
    valid_until TEXT,
    supersedes_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner_key, slot_key, normalized_value_hash)
);

CREATE TABLE IF NOT EXISTS memory_evidence (
    fact_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    start_char INTEGER NOT NULL,
    end_char INTEGER NOT NULL,
    quote_hash TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (fact_id, message_id, start_char, end_char),
    FOREIGN KEY (fact_id) REFERENCES memory_facts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_tombstones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_key TEXT NOT NULL,
    slot_key TEXT NOT NULL,
    blocked_value_hash TEXT,
    reason TEXT NOT NULL,
    forgotten_at TEXT NOT NULL,
    cleared_at TEXT
);

CREATE TABLE IF NOT EXISTS memory_render_state (
    owner_key TEXT PRIMARY KEY,
    revision INTEGER NOT NULL DEFAULT 0,
    file_hash TEXT,
    file_mtime REAL,
    rendered_fact_ids_json TEXT NOT NULL DEFAULT '[]',
    valid_snapshot_body TEXT,
    render_dirty INTEGER NOT NULL DEFAULT 0,
    git_dirty INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS memory_source_barriers (
    conversation_id TEXT NOT NULL,
    deletion_id TEXT NOT NULL,
    deleted_at TEXT NOT NULL,
    PRIMARY KEY (conversation_id, deletion_id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_fact(row: sqlite3.Row) -> dict:
    return dict(row)


class MemoryStore:
    def __init__(self, db_path: str | Path, *, owner_key: str):
        self.db_path = Path(db_path)
        self.owner_key = owner_key
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def upsert_fact(
        self,
        *,
        slot_key: str,
        category: str,
        statement: str,
        normalized_value_hash: str,
        origin: str,
        confidence: float = 1.0,
        sensitivity: str = "normal",
        status: str = "confirmed",
        fact_id: str | None = None,
    ) -> dict:
        now = _now()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM memory_facts
                WHERE owner_key = ? AND slot_key = ? AND normalized_value_hash = ?
                """,
                (self.owner_key, slot_key, normalized_value_hash),
            ).fetchone()
            if existing:
                merged_origin = existing["origin"]
                if ORIGIN_RANK.get(origin, 0) > ORIGIN_RANK.get(existing["origin"], 0):
                    merged_origin = origin
                merged_conf = max(float(existing["confidence"]), float(confidence))
                conn.execute(
                    """
                    UPDATE memory_facts SET
                        statement = ?, category = ?, origin = ?, confidence = ?,
                        sensitivity = ?, status = ?, last_seen_at = ?, updated_at = ?,
                        confirmed_at = COALESCE(confirmed_at, ?)
                    WHERE id = ?
                    """,
                    (
                        statement,
                        category,
                        merged_origin,
                        merged_conf,
                        sensitivity,
                        status,
                        now,
                        now,
                        now if status == "confirmed" else None,
                        existing["id"],
                    ),
                )
                conn.commit()
                out = self.get_fact(existing["id"]) or {}
                if out and out.get("status") in ("confirmed", "candidate", "stale"):
                    self.supersede_others_with_value_hash(
                        out["normalized_value_hash"], keep_id=out["id"]
                    )
                return out

            fid = fact_id or str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO memory_facts (
                    id, owner_key, slot_key, category, statement, normalized_value_hash,
                    status, origin, confidence, sensitivity,
                    first_seen_at, last_seen_at, confirmed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fid,
                    self.owner_key,
                    slot_key,
                    category,
                    statement,
                    normalized_value_hash,
                    status,
                    origin,
                    confidence,
                    sensitivity,
                    now,
                    now,
                    now if status == "confirmed" else None,
                    now,
                    now,
                ),
            )
            conn.commit()
            out = self.get_fact(fid) or {}
            if out and out.get("status") in ("confirmed", "candidate", "stale"):
                self.supersede_others_with_value_hash(
                    out["normalized_value_hash"], keep_id=out["id"]
                )
            return out

    def get_fact(self, fact_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_facts WHERE id = ? AND owner_key = ?",
                (fact_id, self.owner_key),
            ).fetchone()
            return _row_to_fact(row) if row else None

    def list_confirmed(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_facts
                WHERE owner_key = ? AND status = 'confirmed'
                ORDER BY updated_at DESC
                """,
                (self.owner_key,),
            ).fetchall()
            return [_row_to_fact(r) for r in rows]

    def block_value(
        self, *, slot_key: str, normalized_value_hash: str, reason: str = "user_forget"
    ) -> None:
        """将某槽位下的值写入 tombstone（不改 fact 行）。"""
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_tombstones (
                    owner_key, slot_key, blocked_value_hash, reason, forgotten_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (self.owner_key, slot_key, normalized_value_hash, reason, now),
            )
            conn.commit()

    def mark_forgotten(self, fact_id: str, *, reason: str = "user_forget") -> None:
        now = _now()
        fact = self.get_fact(fact_id)
        if not fact:
            return
        with self._connect() as conn:
            conn.execute(
                "UPDATE memory_facts SET status = 'forgotten', updated_at = ? WHERE id = ?",
                (now, fact_id),
            )
            conn.commit()
        self.block_value(
            slot_key=fact["slot_key"],
            normalized_value_hash=fact["normalized_value_hash"],
            reason=reason,
        )

    def clear_tombstone(self, *, slot_key: str, normalized_value_hash: str) -> bool:
        now = _now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE memory_tombstones
                SET cleared_at = ?
                WHERE owner_key = ? AND slot_key = ? AND blocked_value_hash = ?
                  AND cleared_at IS NULL
                """,
                (now, self.owner_key, slot_key, normalized_value_hash),
            )
            conn.commit()
            return cur.rowcount > 0

    def has_tombstone(self, *, slot_key: str, normalized_value_hash: str | None = None) -> bool:
        with self._connect() as conn:
            if normalized_value_hash:
                row = conn.execute(
                    """
                    SELECT 1 FROM memory_tombstones
                    WHERE owner_key = ? AND slot_key = ? AND blocked_value_hash = ?
                      AND cleared_at IS NULL
                    LIMIT 1
                    """,
                    (self.owner_key, slot_key, normalized_value_hash),
                ).fetchone()
                return row is not None
            row = conn.execute(
                """
                SELECT 1 FROM memory_tombstones
                WHERE owner_key = ? AND slot_key = ? AND blocked_value_hash IS NULL
                  AND cleared_at IS NULL
                LIMIT 1
                """,
                (self.owner_key, slot_key),
            ).fetchone()
            return row is not None

    def has_topic_fingerprint_tombstone(self, *, normalized_value_hash: str) -> bool:
        """任意类目下 ``*.topic_{hash[:12]}`` 是否仍阻止该值（防类目漂移绕过）。"""
        return self.has_value_tombstone(normalized_value_hash)

    def clear_topic_fingerprint_tombstones(self, *, normalized_value_hash: str) -> bool:
        """清除该值在任意槽上的 tombstone（显式重新记住）。"""
        return self.clear_value_tombstones(normalized_value_hash)

    def has_value_tombstone(self, normalized_value_hash: str) -> bool:
        """该值在任意槽是否仍被阻止（遗忘后不得经 topic_* 等旁路回潮）。"""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM memory_tombstones
                WHERE owner_key = ? AND blocked_value_hash = ?
                  AND cleared_at IS NULL
                LIMIT 1
                """,
                (self.owner_key, normalized_value_hash),
            ).fetchone()
            return row is not None

    def clear_value_tombstones(self, normalized_value_hash: str) -> bool:
        now = _now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE memory_tombstones
                SET cleared_at = ?
                WHERE owner_key = ? AND blocked_value_hash = ?
                  AND cleared_at IS NULL
                """,
                (now, self.owner_key, normalized_value_hash),
            )
            conn.commit()
            return cur.rowcount > 0

    def reassign_slot_key(self, fact_id: str, new_slot: str) -> dict:
        """将存活条迁到目标槽（migrate 升格 / 同值收敛），保留 id 与出处。"""
        fact = self.get_fact(fact_id)
        if not fact:
            return {}
        new_slot = (new_slot or "").strip()
        if not new_slot or new_slot == fact.get("slot_key"):
            return fact
        self.supersede_others_in_slot(new_slot, keep_id=fact_id)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE memory_facts
                SET normalized_value_hash = normalized_value_hash || ':x:' || id,
                    updated_at = ?
                WHERE owner_key = ? AND slot_key = ? AND normalized_value_hash = ?
                  AND id != ?
                """,
                (now, self.owner_key, new_slot, fact["normalized_value_hash"], fact_id),
            )
            conn.execute(
                "UPDATE memory_facts SET slot_key = ?, updated_at = ? WHERE id = ?",
                (new_slot, now, fact_id),
            )
            conn.commit()
        return self.get_fact(fact_id) or {}

    def add_evidence(
        self,
        *,
        fact_id: str,
        conversation_id: str,
        message_id: str,
        start_char: int,
        end_char: int,
        quote_hash: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO memory_evidence (
                    fact_id, conversation_id, message_id, start_char, end_char,
                    quote_hash, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact_id,
                    conversation_id,
                    message_id,
                    start_char,
                    end_char,
                    quote_hash,
                    _now(),
                ),
            )
            conn.commit()

    def add_session_evidence(self, fact_id: str, conversation_id: str) -> None:
        """会话级出处：每会话每事实最多一条，不记录字级 span。

        同会话重复追加时 INSERT OR IGNORE，仍刷新 last_seen（规格 §5.3 / §7.2）。
        """
        import hashlib

        cid = (conversation_id or "").strip()
        if not cid:
            return
        self.add_evidence(
            fact_id=fact_id,
            conversation_id=cid,
            message_id=f"session:{cid}",
            start_char=0,
            end_char=0,
            quote_hash=hashlib.sha256(f"session:{cid}".encode("utf-8")).hexdigest(),
        )
        self.set_last_seen_at(fact_id)

    def list_evidence(self, fact_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_evidence WHERE fact_id = ? ORDER BY observed_at",
                (fact_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_render_state(self) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_render_state WHERE owner_key = ?",
                (self.owner_key,),
            ).fetchone()
            if not row:
                return {
                    "owner_key": self.owner_key,
                    "revision": 0,
                    "rendered_fact_ids_json": "[]",
                    "render_dirty": 0,
                    "git_dirty": 0,
                }
            return dict(row)

    def save_render_state(
        self,
        *,
        revision: int,
        file_hash: str | None,
        file_mtime: float | None,
        rendered_fact_ids: list[str],
        valid_snapshot_body: str | None,
        render_dirty: bool = False,
        git_dirty: bool = False,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_render_state (
                    owner_key, revision, file_hash, file_mtime, rendered_fact_ids_json,
                    valid_snapshot_body, render_dirty, git_dirty
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_key) DO UPDATE SET
                    revision = excluded.revision,
                    file_hash = excluded.file_hash,
                    file_mtime = excluded.file_mtime,
                    rendered_fact_ids_json = excluded.rendered_fact_ids_json,
                    valid_snapshot_body = excluded.valid_snapshot_body,
                    render_dirty = excluded.render_dirty,
                    git_dirty = excluded.git_dirty
                """,
                (
                    self.owner_key,
                    revision,
                    file_hash,
                    file_mtime,
                    json.dumps(rendered_fact_ids, ensure_ascii=False),
                    valid_snapshot_body,
                    1 if render_dirty else 0,
                    1 if git_dirty else 0,
                ),
            )
            conn.commit()

    def rebind_evidence(self, from_fact_id: str, to_fact_id: str) -> int:
        """将出处从旧 fact 迁到存活 fact（INSERT OR IGNORE 后删旧行）。"""
        src = (from_fact_id or "").strip()
        dst = (to_fact_id or "").strip()
        if not src or not dst or src == dst:
            return 0
        if not self.get_fact(dst):
            return 0
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_evidence WHERE fact_id = ?",
                (src,),
            ).fetchall()
            moved = 0
            for r in rows:
                # UPSERT：主键冲突时仍迁入 quote_hash，避免 OR IGNORE 后删源丢摘录
                conn.execute(
                    """
                    INSERT INTO memory_evidence (
                        fact_id, conversation_id, message_id, start_char, end_char,
                        quote_hash, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(fact_id, message_id, start_char, end_char) DO UPDATE SET
                        conversation_id = excluded.conversation_id,
                        quote_hash = excluded.quote_hash,
                        observed_at = excluded.observed_at
                    """,
                    (
                        dst,
                        r["conversation_id"],
                        r["message_id"],
                        r["start_char"],
                        r["end_char"],
                        r["quote_hash"],
                        r["observed_at"],
                    ),
                )
                moved += 1
            if moved:
                conn.execute(
                    "DELETE FROM memory_evidence WHERE fact_id = ?",
                    (src,),
                )
            conn.commit()
            return moved

    def resolve_supersede_survivor(self, fact_id: str) -> str:
        """沿 supersedes_id 链走到最终存活 id；悬空/环则返回空串。"""
        cur = (fact_id or "").strip()
        if not cur:
            return ""
        seen: set[str] = set()
        while cur and cur not in seen:
            seen.add(cur)
            fact = self.get_fact(cur)
            if not fact:
                return ""
            nxt = (fact.get("supersedes_id") or "").strip()
            if fact.get("status") == "superseded" and nxt:
                cur = nxt
                continue
            return cur
        return ""

    def repair_evidence_following_supersede(self) -> int:
        """存量修复：被 supersede 的 fact 若仍挂 evidence，迁到最终存活 id。"""
        moved = 0
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, supersedes_id FROM memory_facts
                WHERE owner_key = ?
                  AND status = 'superseded'
                  AND supersedes_id IS NOT NULL
                  AND supersedes_id != ''
                """,
                (self.owner_key,),
            ).fetchall()
        for r in rows:
            try:
                survivor = self.resolve_supersede_survivor(r["supersedes_id"])
                if not survivor or survivor == r["id"]:
                    continue
                moved += self.rebind_evidence(r["id"], survivor)
            except Exception:  # noqa: BLE001 — 单行失败不阻断其余
                continue
        return moved

    def mark_superseded(self, fact_id: str, *, supersedes_id: str | None = None) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE memory_facts SET status = 'superseded', supersedes_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (supersedes_id, now, fact_id),
            )
            conn.commit()
        # 出处必须跟着存活画像走，否则面板 conversation_ids 为空、跳转全禁用
        keep = (supersedes_id or "").strip()
        if keep:
            self.rebind_evidence(fact_id, keep)

    def find_stale_by_slot(self, slot_key: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_facts
                WHERE owner_key = ? AND slot_key = ? AND status = 'stale'
                """,
                (self.owner_key, slot_key),
            ).fetchall()
            return [_row_to_fact(r) for r in rows]

    def supersede_others_in_slot(
        self, slot_key: str, *, keep_id: str | None = None
    ) -> int:
        """同槽仅保留 keep_id（confirmed+candidate+stale）；keep_id 为空则全部 supersede。"""
        n = 0
        for fact in self.find_confirmed_by_slot(slot_key):
            if keep_id and fact["id"] == keep_id:
                continue
            self.mark_superseded(fact["id"], supersedes_id=keep_id)
            n += 1
        for cand in self.list_candidates():
            if cand["slot_key"] != slot_key:
                continue
            if keep_id and cand["id"] == keep_id:
                continue
            self.mark_superseded(cand["id"], supersedes_id=keep_id)
            n += 1
        for stale in self.find_stale_by_slot(slot_key):
            if keep_id and stale["id"] == keep_id:
                continue
            self.mark_superseded(stale["id"], supersedes_id=keep_id)
            n += 1
        return n

    def supersede_others_with_value_hash(
        self, normalized_value_hash: str, *, keep_id: str
    ) -> int:
        """同值最多一条存活：灭活其它 confirmed/candidate/stale 并迁出处。"""
        keep = (keep_id or "").strip()
        if not keep or not normalized_value_hash:
            return 0
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id FROM memory_facts
                WHERE owner_key = ? AND normalized_value_hash = ?
                  AND status IN ('confirmed', 'candidate', 'stale')
                  AND id != ?
                """,
                (self.owner_key, normalized_value_hash, keep),
            ).fetchall()
        n = 0
        for r in rows:
            self.mark_superseded(r["id"], supersedes_id=keep)
            n += 1
        return n

    def count_evidence(self, fact_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM memory_evidence WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            return int(row["n"]) if row else 0

    def count_distinct_conversation_evidence(self, fact_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT conversation_id) AS n
                FROM memory_evidence WHERE fact_id = ?
                """,
                (fact_id,),
            ).fetchone()
            return int(row["n"]) if row else 0

    def find_confirmed_by_slot(self, slot_key: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_facts
                WHERE owner_key = ? AND slot_key = ? AND status = 'confirmed'
                """,
                (self.owner_key, slot_key),
            ).fetchall()
            return [_row_to_fact(r) for r in rows]

    def find_by_slot_and_hash(self, slot_key: str, normalized_value_hash: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM memory_facts
                WHERE owner_key = ? AND slot_key = ? AND normalized_value_hash = ?
                """,
                (self.owner_key, slot_key, normalized_value_hash),
            ).fetchone()
            return _row_to_fact(row) if row else None

    def find_active_by_value_hash(self, normalized_value_hash: str) -> dict | None:
        """任意槽上同值存活条（含跨类目 topic 迁槽后），供并入防平行开槽。"""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM memory_facts
                WHERE owner_key = ? AND normalized_value_hash = ?
                  AND status IN ('confirmed', 'candidate', 'stale')
                ORDER BY
                    CASE status
                        WHEN 'confirmed' THEN 0
                        WHEN 'candidate' THEN 1
                        ELSE 2
                    END,
                    updated_at DESC
                LIMIT 1
                """,
                (self.owner_key, normalized_value_hash),
            ).fetchone()
            return _row_to_fact(row) if row else None

    def list_candidates(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_facts
                WHERE owner_key = ? AND status = 'candidate'
                ORDER BY updated_at DESC
                """,
                (self.owner_key,),
            ).fetchall()
            return [_row_to_fact(r) for r in rows]

    def set_status(self, fact_id: str, status: str) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE memory_facts SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, fact_id),
            )
            conn.commit()

    def update_fact_content(
        self,
        fact_id: str,
        *,
        statement: str,
        normalized_value_hash: str,
        category: str | None = None,
        origin: str | None = None,
        confidence: float | None = None,
        sensitivity: str | None = None,
        status: str | None = None,
    ) -> dict:
        """就地更新 statement（merge/replace 保 id 与 evidence）。"""
        now = _now()
        fact = self.get_fact(fact_id)
        if not fact:
            return {}
        with self._connect() as conn:
            # 释放同槽其它行占用的唯一键（含 stale/candidate），避免 hash 冲突
            conn.execute(
                """
                UPDATE memory_facts
                SET normalized_value_hash = normalized_value_hash || ':x:' || id,
                    updated_at = ?
                WHERE owner_key = ? AND slot_key = ? AND normalized_value_hash = ?
                  AND id != ?
                """,
                (now, self.owner_key, fact["slot_key"], normalized_value_hash, fact_id),
            )
            conn.execute(
                """
                UPDATE memory_facts SET
                    statement = ?,
                    normalized_value_hash = ?,
                    category = COALESCE(?, category),
                    origin = COALESCE(?, origin),
                    confidence = COALESCE(?, confidence),
                    sensitivity = COALESCE(?, sensitivity),
                    status = COALESCE(?, status),
                    last_seen_at = ?,
                    updated_at = ?,
                    confirmed_at = CASE
                        WHEN COALESCE(?, status) = 'confirmed'
                        THEN COALESCE(confirmed_at, ?)
                        ELSE confirmed_at
                    END
                WHERE id = ?
                """,
                (
                    statement,
                    normalized_value_hash,
                    category,
                    origin,
                    confidence,
                    sensitivity,
                    status,
                    now,
                    now,
                    status,
                    now,
                    fact_id,
                ),
            )
            conn.commit()
        # topic_* 槽名嵌入内容指纹：statement 变更后须迁槽，避免平行开第二条
        updated = self.sync_topic_slot_key(fact_id)
        # 任意槽改句后旧值必须 tombstone，否则会话 replace/merge 后旧表述
        # 可再对齐回原槽并覆盖更正结果（手动 edit/correct 亦 block，幂等）
        if fact["normalized_value_hash"] != normalized_value_hash:
            self.block_value(
                slot_key=fact.get("slot_key") or "",
                normalized_value_hash=fact["normalized_value_hash"],
                reason="superseded",
            )
        if updated and updated.get("status") in ("confirmed", "candidate", "stale"):
            self.supersede_others_with_value_hash(
                updated["normalized_value_hash"], keep_id=fact_id
            )
        return updated

    def sync_topic_slot_key(self, fact_id: str) -> dict:
        """若为 ``*.topic_*`` 开放槽，使 slot_key 与当前 statement 指纹一致。"""
        from app.engine.memory.normalize import value_hash

        fact = self.get_fact(fact_id)
        if not fact:
            return {}
        sk = fact.get("slot_key") or ""
        if ".topic_" not in sk:
            return fact
        cat = (fact.get("category") or sk.split(".", 1)[0] or "preference").strip().lower()
        new_slot = f"{cat}.topic_{value_hash(fact['statement'])[:12]}"
        if new_slot == sk:
            return fact
        # 目标槽若已有其它存活条，先灭活并迁出处
        self.supersede_others_in_slot(new_slot, keep_id=fact_id)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE memory_facts
                SET normalized_value_hash = normalized_value_hash || ':x:' || id,
                    updated_at = ?
                WHERE owner_key = ? AND slot_key = ? AND normalized_value_hash = ?
                  AND id != ?
                """,
                (now, self.owner_key, new_slot, fact["normalized_value_hash"], fact_id),
            )
            conn.execute(
                "UPDATE memory_facts SET slot_key = ?, updated_at = ? WHERE id = ?",
                (new_slot, now, fact_id),
            )
            conn.commit()
        return self.get_fact(fact_id) or {}

    def set_last_seen_at(self, fact_id: str, ts: str | None = None) -> None:
        stamp = ts or _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE memory_facts SET last_seen_at = ?, updated_at = ? WHERE id = ?",
                (stamp, stamp, fact_id),
            )
            conn.commit()

    def list_active_facts(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_facts
                WHERE owner_key = ? AND status IN ('confirmed', 'candidate', 'stale')
                ORDER BY updated_at DESC
                """,
                (self.owner_key,),
            ).fetchall()
            return [_row_to_fact(r) for r in rows]

    def search_confirmed(self, query: str, *, limit: int = 10) -> list[dict]:
        q = (query or "").strip().lower()
        facts = self.list_confirmed()
        if not q:
            return facts[:limit]
        matched = [f for f in facts if q in f["statement"].lower() or q in f["slot_key"].lower()]
        return matched[:limit]
