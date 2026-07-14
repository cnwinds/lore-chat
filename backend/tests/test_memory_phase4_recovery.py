from datetime import datetime, timedelta, timezone

from app.engine.memory.normalize import normalize_slot_key, value_hash
from app.engine.memory.observer import MemoryObserver
from app.engine.memory.store import MemoryStore


def test_stale_recovers_on_new_evidence(tmp_path):
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    stmt = "我偏好简洁回答"
    vhash = value_hash(stmt)
    slot = normalize_slot_key("preference", stmt)
    fact = store.upsert_fact(
        slot_key=slot,
        category="preference",
        statement=stmt,
        normalized_value_hash=vhash,
        origin="direct",
        status="stale",
    )
    observer = MemoryObserver(store)
    observer.observe_message(stmt, conversation_id="c1", message_id="m1")
    updated = store.get_fact(fact["id"])
    assert updated["status"] == "confirmed"
