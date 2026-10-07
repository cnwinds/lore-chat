from app.engine.memory.normalize import normalize_slot_key, value_hash
from app.engine.memory.store import MemoryStore


def test_upsert_fact_idempotent(tmp_path):
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    slot = normalize_slot_key("preference", "默认使用中文")
    h = value_hash("默认使用中文")
    f1 = store.upsert_fact(
        slot_key=slot,
        category="preference",
        statement="默认使用中文",
        normalized_value_hash=h,
        origin="explicit_remember",
        confidence=1.0,
    )
    f2 = store.upsert_fact(
        slot_key=slot,
        category="preference",
        statement="默认使用中文",
        normalized_value_hash=h,
        origin="manual",
        confidence=1.0,
    )
    assert f1["id"] == f2["id"]
    assert f2["origin"] == "manual"


def test_init_drops_legacy_render_state(tmp_path):
    import sqlite3

    db = tmp_path / "memory.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE memory_render_state (owner_key TEXT PRIMARY KEY, revision INTEGER)"
    )
    conn.execute(
        "INSERT INTO memory_render_state (owner_key, revision) VALUES ('ws1', 4)"
    )
    conn.commit()
    conn.close()

    store = MemoryStore(db, owner_key="ws1")
    with store._connect() as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "memory_render_state" not in names
    assert "memory_facts" in names

    fresh = MemoryStore(tmp_path / "fresh.db", owner_key="ws1")
    with fresh._connect() as conn:
        fresh_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "memory_render_state" not in fresh_names


def test_list_confirmed_excludes_forgotten(tmp_path):
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    f = store.upsert_fact(
        slot_key="preference.lang",
        category="preference",
        statement="中文",
        normalized_value_hash=value_hash("中文"),
        origin="manual",
    )
    store.mark_forgotten(f["id"], reason="user_forget")
    assert store.list_confirmed() == []
