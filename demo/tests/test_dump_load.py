import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.dump import dump_conversations, dump_memory, write_dump
from tools.load import load_conversations, load_memory

CONV_DDL = """
CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  active_turn_id TEXT, indexed_dirty INTEGER NOT NULL DEFAULT 0);
CREATE TABLE messages (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
  seq INTEGER NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL DEFAULT '',
  ts TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'complete',
  client_message_id TEXT, in_reply_to_message_id TEXT, timeline_json TEXT,
  sources_json TEXT, total_duration_ms INTEGER, doc_context_json TEXT,
  attachments_json TEXT, primary_doc TEXT, model_name TEXT,
  model_failover INTEGER NOT NULL DEFAULT 0, web_enabled INTEGER);
CREATE TABLE turns (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
  client_message_id TEXT NOT NULL, user_message_id TEXT NOT NULL,
  assistant_message_id TEXT, status TEXT NOT NULL DEFAULT 'running',
  observation_allowed INTEGER NOT NULL DEFAULT 0, locked_by TEXT,
  locked_until TEXT, started_at TEXT NOT NULL, finalized_at TEXT);
CREATE TABLE conversation_summaries (id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id TEXT NOT NULL, doc_path TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1, covered_through_message_id TEXT,
  status TEXT NOT NULL DEFAULT 'current', is_primary INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL);
CREATE TABLE conversation_system_events (id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL, event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL, created_at TEXT NOT NULL);
"""

MEM_DDL = """
CREATE TABLE memory_facts (id TEXT PRIMARY KEY, owner_key TEXT NOT NULL,
  slot_key TEXT NOT NULL, category TEXT NOT NULL, statement TEXT NOT NULL,
  normalized_value_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'confirmed',
  origin TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 1.0,
  sensitivity TEXT NOT NULL DEFAULT 'normal', first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL, confirmed_at TEXT, valid_until TEXT,
  supersedes_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE memory_evidence (fact_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
  message_id TEXT NOT NULL, start_char INTEGER NOT NULL, end_char INTEGER NOT NULL,
  quote_hash TEXT NOT NULL, observed_at TEXT NOT NULL);
"""


def _seed_conv(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(CONV_DDL)
    conn.execute(
        "INSERT INTO conversations VALUES ('c1','选型','2026-08-18T00:00:00+00:00',"
        "'2026-08-18T01:00:00+00:00',NULL,0)"
    )
    conn.execute(
        "INSERT INTO messages (id,conversation_id,seq,role,text,ts) "
        "VALUES ('m1','c1',1,'user','向量库怎么选','2026-08-18T00:10:00+00:00')"
    )
    conn.commit()
    conn.close()


def _seed_mem(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(MEM_DDL)
    conn.execute(
        "INSERT INTO memory_facts VALUES ('f1','w1','identity','identity',"
        "'独立开发者','h1','confirmed','user',1.0,'normal',"
        "'2026-08-18T00:00:00+00:00','2026-08-18T00:00:00+00:00',NULL,NULL,NULL,"
        "'2026-08-18T00:00:00+00:00','2026-08-18T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()


def test_dump_conversations_groups_by_conversation(tmp_path):
    db = tmp_path / "conversations.db"
    _seed_conv(db)
    out = dump_conversations(db)
    assert len(out) == 1
    assert out[0]["conversation"]["id"] == "c1"
    assert out[0]["messages"][0]["text"] == "向量库怎么选"


def test_dump_memory_returns_facts(tmp_path):
    db = tmp_path / "memory.db"
    _seed_mem(db)
    out = dump_memory(db)
    assert out["facts"][0]["statement"] == "独立开发者"


def test_write_dump_emits_one_json_per_conversation(tmp_path):
    kb = tmp_path / "knowledge"
    (kb / ".kb" / "conversations").mkdir(parents=True)
    (kb / ".kb" / "memory").mkdir(parents=True)
    _seed_conv(kb / ".kb" / "conversations" / "conversations.db")
    _seed_mem(kb / ".kb" / "memory" / "memory.db")
    out_dir = tmp_path / "content"
    write_dump(kb, out_dir)
    assert (out_dir / "conversations" / "c1.json").is_file()
    assert json.loads((out_dir / "memory.json").read_text(encoding="utf-8"))["facts"]


def test_load_roundtrip_restores_rows(tmp_path):
    src = tmp_path / "src.db"
    _seed_conv(src)
    payloads = dump_conversations(src)

    dst = tmp_path / "dst.db"
    conn = sqlite3.connect(dst)
    conn.executescript(CONV_DDL)
    conn.commit()
    conn.close()

    load_conversations(dst, payloads)
    conn = sqlite3.connect(dst)
    rows = conn.execute("SELECT id, text FROM messages").fetchall()
    conn.close()
    assert rows == [("m1", "向量库怎么选")]


def test_load_memory_roundtrip(tmp_path):
    src = tmp_path / "src.db"
    _seed_mem(src)
    payload = dump_memory(src)

    dst = tmp_path / "dst.db"
    conn = sqlite3.connect(dst)
    conn.executescript(MEM_DDL)
    conn.commit()
    conn.close()

    load_memory(dst, payload)
    conn = sqlite3.connect(dst)
    rows = conn.execute("SELECT statement FROM memory_facts").fetchall()
    conn.close()
    assert rows == [("独立开发者",)]


def test_load_memory_rewrites_owner_key(tmp_path):
    """owner_key 随 KB 生成；不改写则记忆面板按当前 workspace 查不到事实。"""
    src = tmp_path / "src.db"
    _seed_mem(src)
    payload = dump_memory(src)

    dst = tmp_path / "dst.db"
    conn = sqlite3.connect(dst)
    conn.executescript(MEM_DDL)
    conn.commit()
    conn.close()

    load_memory(dst, payload, owner_key="w2")
    conn = sqlite3.connect(dst)
    rows = conn.execute("SELECT owner_key FROM memory_facts").fetchall()
    conn.close()
    assert rows == [("w2",)]


def test_load_is_idempotent(tmp_path):
    src = tmp_path / "src.db"
    _seed_conv(src)
    payloads = dump_conversations(src)
    dst = tmp_path / "dst.db"
    conn = sqlite3.connect(dst)
    conn.executescript(CONV_DDL)
    conn.commit()
    conn.close()

    load_conversations(dst, payloads)
    load_conversations(dst, payloads)
    conn = sqlite3.connect(dst)
    count = conn.execute("SELECT count(*) FROM messages").fetchone()[0]
    conn.close()
    assert count == 1
