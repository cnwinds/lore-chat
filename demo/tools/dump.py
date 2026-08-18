"""KB 的 SQLite → 可 diff 的 JSON。会话与记忆因此能被人工编辑与 review。"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

CONVERSATION_TABLES = (
    "messages",
    "turns",
    "conversation_summaries",
    "conversation_system_events",
)

CONVERSATIONS_DB_REL = Path(".kb") / "conversations" / "conversations.db"
MEMORY_DB_REL = Path(".kb") / "memory" / "memory.db"


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def dump_conversations(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    try:
        out: list[dict] = []
        for conv in _rows(conn, "SELECT * FROM conversations ORDER BY created_at"):
            payload = {"conversation": conv}
            for table in CONVERSATION_TABLES:
                order = " ORDER BY seq" if table == "messages" else ""
                payload[table] = _rows(
                    conn,
                    f"SELECT * FROM {table} WHERE conversation_id = ?{order}",
                    (conv["id"],),
                )
            out.append(payload)
        return out
    finally:
        conn.close()


def dump_memory(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        return {
            "facts": _rows(conn, "SELECT * FROM memory_facts ORDER BY created_at"),
            "evidence": _rows(conn, "SELECT * FROM memory_evidence"),
        }
    finally:
        conn.close()


def write_dump(kb_path: Path, out_dir: Path) -> None:
    conv_dir = out_dir / "conversations"
    conv_dir.mkdir(parents=True, exist_ok=True)
    for payload in dump_conversations(kb_path / CONVERSATIONS_DB_REL):
        cid = payload["conversation"]["id"]
        (conv_dir / f"{cid}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    memory = dump_memory(kb_path / MEMORY_DB_REL)
    (out_dir / "memory.json").write_text(
        json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="导出演示会话与记忆为 JSON")
    parser.add_argument("--kb", required=True, type=Path, help="实例的 KB 目录")
    parser.add_argument("--out", required=True, type=Path, help="输出目录（通常是 demo/）")
    args = parser.parse_args()
    write_dump(args.kb, args.out)
    print(f"已导出到 {args.out}")


if __name__ == "__main__":
    main()
