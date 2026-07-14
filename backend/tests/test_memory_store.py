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
