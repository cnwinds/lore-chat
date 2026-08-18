import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build import materialize


def _content(tmp_path: Path) -> Path:
    content = tmp_path / "content"
    (content / "knowledge" / "技术").mkdir(parents=True)
    (content / "knowledge" / "技术" / "a.md").write_text("# A\n正文\n", encoding="utf-8")
    (content / "conversations").mkdir(parents=True)
    (content / "conversations" / "c1.json").write_text(
        json.dumps(
            {
                "conversation": {
                    "id": "c1",
                    "title": "选型",
                    "created_at": "2026-08-18T00:00:00+00:00",
                    "updated_at": "2026-08-18T01:00:00+00:00",
                    "active_turn_id": None,
                    "indexed_dirty": 0,
                },
                "messages": [
                    {
                        "id": "m1",
                        "conversation_id": "c1",
                        "seq": 1,
                        "role": "user",
                        "text": "向量库怎么选",
                        "ts": "2026-08-18T00:10:00+00:00",
                        "status": "complete",
                    }
                ],
                "turns": [],
                "conversation_summaries": [],
                "conversation_system_events": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (content / "memory.json").write_text(
        json.dumps({"facts": [], "evidence": []}), encoding="utf-8"
    )
    (content / "manifest.json").write_text(
        json.dumps({"format_version": 1, "reference_date": "2026-08-18"}),
        encoding="utf-8",
    )
    return content


def test_materialize_copies_markdown(tmp_path):
    content = _content(tmp_path)
    kb = tmp_path / "knowledge"
    materialize(content, kb, today=date(2026, 8, 18), reindex=False)
    assert (kb / "技术" / "a.md").read_text(encoding="utf-8").startswith("# A")


def test_materialize_loads_conversations(tmp_path):
    content = _content(tmp_path)
    kb = tmp_path / "knowledge"
    materialize(content, kb, today=date(2026, 8, 18), reindex=False)
    conn = sqlite3.connect(kb / ".kb" / "conversations" / "conversations.db")
    rows = conn.execute("SELECT id FROM conversations").fetchall()
    conn.close()
    assert rows == [("c1",)]


def test_materialize_shifts_timestamps(tmp_path):
    content = _content(tmp_path)
    kb = tmp_path / "knowledge"
    result = materialize(content, kb, today=date(2026, 9, 17), reindex=False)
    assert result["offset_days"] == 30
    conn = sqlite3.connect(kb / ".kb" / "conversations" / "conversations.db")
    ts = conn.execute("SELECT ts FROM messages WHERE id='m1'").fetchone()[0]
    conn.close()
    assert ts.startswith("2026-09-17")


def test_materialize_wipes_previous_drift(tmp_path):
    content = _content(tmp_path)
    kb = tmp_path / "knowledge"
    kb.mkdir(parents=True)
    (kb / "脏文件.md").write_text("访客留下的漂移", encoding="utf-8")
    materialize(content, kb, today=date(2026, 8, 18), reindex=False)
    assert not (kb / "脏文件.md").exists()


def test_materialize_is_repeatable(tmp_path):
    content = _content(tmp_path)
    kb = tmp_path / "knowledge"
    first = materialize(content, kb, today=date(2026, 8, 18), reindex=False)
    second = materialize(content, kb, today=date(2026, 8, 18), reindex=False)
    assert first == second


def test_materialize_binds_memory_to_runtime_workspace(tmp_path):
    """定稿实例的 workspace id 与演示站不同；不改写则记忆面板查不到事实。"""
    content = _content(tmp_path)
    (content / "memory.json").write_text(
        json.dumps(
            {
                "facts": [
                    {
                        "id": "f1",
                        "owner_key": "定稿实例的旧 id",
                        "slot_key": "identity",
                        "category": "identity",
                        "statement": "独立开发者，在做面向教培场景的 AI 学习产品",
                        "normalized_value_hash": "h1",
                        "status": "confirmed",
                        "origin": "user",
                        "confidence": 1.0,
                        "sensitivity": "normal",
                        "first_seen_at": "2026-08-18T00:00:00+00:00",
                        "last_seen_at": "2026-08-18T00:00:00+00:00",
                        "created_at": "2026-08-18T00:00:00+00:00",
                        "updated_at": "2026-08-18T00:00:00+00:00",
                    }
                ],
                "evidence": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    kb = tmp_path / "knowledge"
    materialize(content, kb, today=date(2026, 8, 18), reindex=False)

    workspace_id = json.loads(
        (kb / ".kb" / "workspace.json").read_text(encoding="utf-8")
    )["workspace_id"]
    conn = sqlite3.connect(kb / ".kb" / "memory" / "memory.db")
    rows = conn.execute("SELECT owner_key FROM memory_facts").fetchall()
    conn.close()
    assert rows == [(workspace_id,)]
