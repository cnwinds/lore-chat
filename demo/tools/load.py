"""JSON → KB 的 SQLite。表结构由 app 侧建好，这里只灌数据。"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from tools.dump import CONVERSATIONS_DB_REL, MEMORY_DB_REL
from tools.timeshift import shift_in_place

TIMESTAMP_KEYS = {
    "created_at",
    "updated_at",
    "ts",
    "started_at",
    "finalized_at",
    "observed_at",
    "first_seen_at",
    "last_seen_at",
    "confirmed_at",
}


def _upsert(conn: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    for row in rows:
        cols = ", ".join(row.keys())
        marks = ", ".join("?" for _ in row)
        conn.execute(
            f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})",
            tuple(row.values()),
        )


def load_conversations(db_path: Path, payloads: list[dict]) -> None:
    conn = sqlite3.connect(db_path)
    try:
        for payload in payloads:
            _upsert(conn, "conversations", [payload["conversation"]])
            for table in (
                "messages",
                "turns",
                "conversation_summaries",
                "conversation_system_events",
            ):
                _upsert(conn, table, payload.get(table) or [])
        conn.commit()
    finally:
        conn.close()


def load_memory(db_path: Path, payload: dict, owner_key: str | None = None) -> None:
    facts = payload.get("facts") or []
    if owner_key:
        # owner_key 是随 KB 生成的 workspace id，定稿实例与演示站不同；
        # 不改写则记忆面板按当前 workspace 查不到任何事实。
        for fact in facts:
            if "owner_key" in fact:
                fact["owner_key"] = owner_key
    conn = sqlite3.connect(db_path)
    try:
        _upsert(conn, "memory_facts", facts)
        _upsert(conn, "memory_evidence", payload.get("evidence") or [])
        conn.commit()
    finally:
        conn.close()


def read_and_load(
    kb_path: Path,
    content_dir: Path,
    offset_days: int = 0,
    owner_key: str | None = None,
) -> None:
    payloads = []
    conv_dir = content_dir / "conversations"
    if conv_dir.is_dir():
        for path in sorted(conv_dir.glob("*.json")):
            payloads.append(json.loads(path.read_text(encoding="utf-8")))
    shift_in_place(payloads, offset_days, TIMESTAMP_KEYS)
    load_conversations(kb_path / CONVERSATIONS_DB_REL, payloads)

    memory_file = content_dir / "memory.json"
    if memory_file.is_file():
        memory = json.loads(memory_file.read_text(encoding="utf-8"))
        shift_in_place(memory, offset_days, TIMESTAMP_KEYS)
        load_memory(kb_path / MEMORY_DB_REL, memory, owner_key=owner_key)


def main() -> None:
    parser = argparse.ArgumentParser(description="把 JSON 会话与记忆导回实例")
    parser.add_argument("--kb", required=True, type=Path)
    parser.add_argument("--content", required=True, type=Path, help="通常是 demo/")
    parser.add_argument("--offset-days", type=int, default=0)
    parser.add_argument(
        "--owner-key",
        default=None,
        help="目标实例的 workspace id；给出时改写记忆事实的 owner_key",
    )
    args = parser.parse_args()
    read_and_load(args.kb, args.content, args.offset_days, owner_key=args.owner_key)
    print(f"已导入到 {args.kb}")


if __name__ == "__main__":
    main()
