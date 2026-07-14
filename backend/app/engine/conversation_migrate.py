"""JSON 分片会话存储 → SQLite `conversations.db` 的一次性、幂等迁移。

旧版存储格式：`<root>/index.json`（`{conversation_id: date}`）+
`<root>/<date>.json`（`{conversation_id: conversation_dict}`）。迁移把这些分片
写入与 `ConversationStore` 相同 schema 的 SQLite 数据库，之后 JSON 文件仅作为
只读留存（不删除、不再作为写路径）。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

from .conversations import _SCHEMA, _dumps, _now

MIGRATION_KEY = "json_shards_v1"

# 固定命名空间：保证同一分片多次迁移得到完全相同的消息 ID（幂等）。
_MESSAGE_ID_NAMESPACE = uuid.UUID("d92f9db4-6f21-4bd1-8f7d-9e2e1a5cf6a1")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rebuild_assistant_text(msg: dict) -> str:
    """助手文本：优先拼接 timeline 中 type==text 的 content；无 timeline 时回退到 text 字段。"""
    parts: list[str] = []
    for block in msg.get("timeline") or []:
        if block.get("type") == "text" and block.get("content"):
            part = str(block["content"]).strip()
            if part:
                parts.append(part)
    if parts:
        return "\n\n".join(parts)
    return str(msg.get("text") or "")


def _message_id(cid: str, seq: int, role: str, ts: str, text: str, timeline_json: str | None) -> str:
    text_hash = _sha256(text or "")
    timeline_hash = _sha256(timeline_json or "")
    name = f"{cid}|{seq}|{role}|{ts}|{text_hash}|{timeline_hash}"
    return str(uuid.uuid5(_MESSAGE_ID_NAMESPACE, name))


def _load_index(root: Path) -> dict[str, str]:
    index_path = root / "index.json"
    if not index_path.exists():
        return {}
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _load_shard(root: Path, date: str, cache: dict[str, dict]) -> dict:
    if date in cache:
        return cache[date]
    shard_path = root / f"{date}.json"
    if shard_path.exists():
        try:
            data = json.loads(shard_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    cache[date] = data if isinstance(data, dict) else {}
    return cache[date]


def _conversation_exists(conn: sqlite3.Connection, cid: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM conversations WHERE id = ? LIMIT 1", (cid,)
    ).fetchone()
    return row is not None


def _migrate_conversation(conn: sqlite3.Connection, cid: str, conv: dict) -> int:
    if _conversation_exists(conn, cid):
        return 0

    created_at = conv.get("created_at") or _now()
    updated_at = conv.get("updated_at") or created_at
    conn.execute(
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

    last_user_msg_id: str | None = None
    last_msg_id: str | None = None
    last_msg_ts: str | None = None
    n_messages = 0

    for seq, msg in enumerate(conv.get("messages", []), start=1):
        role = msg.get("role", "user")
        ts = msg.get("ts") or created_at
        timeline = msg.get("timeline")
        timeline_json = _dumps(timeline) if timeline is not None else None

        if role == "assistant":
            text = _rebuild_assistant_text(msg)
        else:
            text = str(msg.get("text") or "")

        msg_id = _message_id(cid, seq, role, ts, text, timeline_json)

        in_reply_to = msg.get("in_reply_to_message_id")
        if role == "assistant" and last_user_msg_id and not in_reply_to:
            in_reply_to = last_user_msg_id

        conn.execute(
            """
            INSERT OR IGNORE INTO messages(
                id, conversation_id, seq, role, text, ts, status,
                client_message_id, in_reply_to_message_id, timeline_json,
                sources_json, total_duration_ms, doc_context_json,
                attachments_json, primary_doc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                msg_id,
                cid,
                seq,
                role,
                text,
                ts,
                msg.get("status") or "complete",
                msg.get("client_message_id"),
                in_reply_to,
                timeline_json,
                _dumps(msg.get("sources")) if msg.get("sources") is not None else None,
                msg.get("total_duration_ms"),
                _dumps(msg.get("doc_context")) if msg.get("doc_context") is not None else None,
                _dumps(msg.get("attachments")) if msg.get("attachments") is not None else None,
                msg.get("primary_doc"),
            ),
        )
        _enqueue_index_fts(conn, msg_id)

        if role == "user":
            last_user_msg_id = msg_id
        last_msg_id = msg_id
        last_msg_ts = ts
        n_messages += 1

    if conv.get("summarized") and conv.get("summary_path"):
        _migrate_summary(conn, cid, conv, last_msg_id, last_msg_ts)

    return n_messages


def _migrate_summary(
    conn: sqlite3.Connection,
    cid: str,
    conv: dict,
    last_msg_id: str | None,
    last_msg_ts: str | None,
) -> None:
    summarized_at = conv.get("summarized_at")
    # 旧格式没有记录“摘要覆盖到哪条消息”，只有当摘要时间可证明晚于（或不早于）
    # 最后一条消息时，才能认为摘要仍覆盖全部历史；否则标记为 stale，等待重新归档。
    if summarized_at and last_msg_ts and summarized_at >= last_msg_ts:
        status = "current"
        covered_through = last_msg_id
    else:
        status = "stale"
        covered_through = None

    conn.execute(
        """
        INSERT INTO conversation_summaries(
            conversation_id, doc_path, revision, covered_through_message_id,
            status, is_primary, created_at
        ) VALUES (?, ?, 1, ?, ?, 1, ?)
        """,
        (
            cid,
            conv["summary_path"],
            covered_through,
            status,
            summarized_at or _now(),
        ),
    )


def _enqueue_index_fts(conn: sqlite3.Connection, message_id: str) -> None:
    now = _now()
    conn.execute(
        """
        INSERT INTO derivation_outbox(
            kind, source_message_id, source_revision, turn_id,
            status, attempts, next_run_at, created_at, updated_at
        ) VALUES ('index_fts', ?, 1, NULL, 'pending', 0, ?, ?, ?)
        """,
        (message_id, now, now, now),
    )


def migrate_json_shards(root: str | Path) -> dict:
    """把 `root` 下的 `index.json` + 日期分片 JSON 迁移进同目录的 `conversations.db`。

    幂等：若 `migration_meta` 已记录 `json_shards_v1` 完成，直接返回统计，不重新扫描
    JSON 文件、不重新插入数据。若 meta 缺失但会话行已存在，同样跳过该会话的插入
    （消息 ID 为内容确定性哈希，摘要与 outbox 通过会话存在性守卫避免重复）。
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "conversations.db"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(_SCHEMA)
        conn.commit()

        already = conn.execute(
            "SELECT value FROM migration_meta WHERE key = ?", (MIGRATION_KEY,)
        ).fetchone()
        if already is not None:
            n_conv = conn.execute("SELECT COUNT(*) AS n FROM conversations").fetchone()["n"]
            n_msg = conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
            return {"conversations": int(n_conv), "messages": int(n_msg), "skipped": True}

        conv_dates = _load_index(root)
        shard_cache: dict[str, dict] = {}
        n_conversations = 0
        n_messages = 0

        for cid, date in conv_dates.items():
            shard = _load_shard(root, date, shard_cache)
            conv = shard.get(cid)
            if conv is None:
                continue
            n_messages += _migrate_conversation(conn, cid, conv)
            n_conversations += 1

        conn.execute(
            "INSERT OR REPLACE INTO migration_meta(key, value) VALUES (?, ?)",
            (MIGRATION_KEY, _now()),
        )
        conn.commit()
        return {"conversations": n_conversations, "messages": n_messages, "skipped": False}
    finally:
        conn.close()
