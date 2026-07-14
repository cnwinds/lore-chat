import json
import sqlite3
from pathlib import Path

from app.engine.conversation_migrate import MIGRATION_KEY, migrate_json_shards
from app.engine.conversations import ConversationStore


def _write_shard(dir: Path, date: str, convs: dict):
    dir.mkdir(parents=True, exist_ok=True)
    (dir / "index.json").write_text(
        json.dumps({cid: date for cid in convs}, ensure_ascii=False),
        encoding="utf-8",
    )
    (dir / f"{date}.json").write_text(
        json.dumps(convs, ensure_ascii=False), encoding="utf-8"
    )


def test_migrate_is_idempotent_and_rebuilds_assistant_text(tmp_path):
    root = tmp_path / "conversations"
    cid = "abc123"
    _write_shard(
        root,
        "2026-07-12",
        {
            cid: {
                "id": cid,
                "title": "旧会话",
                "created_at": "2026-07-12T10:00:00",
                "updated_at": "2026-07-12T10:01:00",
                "messages": [
                    {"role": "user", "text": "你好", "ts": "2026-07-12T10:00:00"},
                    {
                        "role": "assistant",
                        "ts": "2026-07-12T10:00:30",
                        "timeline": [
                            {"type": "text", "content": "你好呀", "ts": "t"}
                        ],
                        "sources": [],
                    },
                ],
                "summarized": True,
                "summary_path": "主题/旧.md",
            }
        },
    )
    r1 = migrate_json_shards(root)
    r2 = migrate_json_shards(root)
    assert r1["conversations"] == 1
    assert r2["conversations"] == 1
    store = ConversationStore(root)
    conv = store.get(cid)
    assert conv["messages"][0]["id"] == store.get(cid)["messages"][0]["id"]
    assert conv["messages"][1]["text"] == "你好呀"
    assert any(s.get("doc_path") == "主题/旧.md" for s in store.list_summaries(cid))


def test_rerun_without_migration_meta_does_not_duplicate_summaries_or_outbox(tmp_path):
    root = tmp_path / "conversations"
    cid = "abc123"
    _write_shard(
        root,
        "2026-07-12",
        {
            cid: {
                "id": cid,
                "title": "旧会话",
                "created_at": "2026-07-12T10:00:00",
                "updated_at": "2026-07-12T10:01:00",
                "messages": [
                    {"role": "user", "text": "你好", "ts": "2026-07-12T10:00:00"},
                    {
                        "role": "assistant",
                        "ts": "2026-07-12T10:00:30",
                        "timeline": [
                            {"type": "text", "content": "你好呀", "ts": "t"}
                        ],
                        "sources": [],
                    },
                ],
                "summarized": True,
                "summary_path": "主题/旧.md",
            }
        },
    )
    migrate_json_shards(root)

    db_path = root / "conversations.db"
    conn = sqlite3.connect(str(db_path))
    try:
        summary_count = conn.execute(
            "SELECT COUNT(*) FROM conversation_summaries"
        ).fetchone()[0]
        outbox_count = conn.execute(
            "SELECT COUNT(*) FROM derivation_outbox"
        ).fetchone()[0]
        conn.execute("DELETE FROM migration_meta WHERE key = ?", (MIGRATION_KEY,))
        conn.commit()
    finally:
        conn.close()

    migrate_json_shards(root)

    conn = sqlite3.connect(str(db_path))
    try:
        assert (
            conn.execute("SELECT COUNT(*) FROM conversation_summaries").fetchone()[0]
            == summary_count
        )
        assert (
            conn.execute("SELECT COUNT(*) FROM derivation_outbox").fetchone()[0]
            == outbox_count
        )
        assert conn.execute(
            "SELECT value FROM migration_meta WHERE key = ?", (MIGRATION_KEY,)
        ).fetchone() is not None
    finally:
        conn.close()
