from datetime import datetime, timedelta, timezone

from app.engine.conversations import ConversationStore
from app.engine.memory.decay import DecayConfig
from app.engine.memory.store import MemoryStore
from app.engine.memory_maintenance import MemoryMaintenanceJob


def _old_ts(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_maintenance_emits_decay_event(tmp_path):
    mem = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    conv = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    cid = conv.create()
    fact = mem.upsert_fact(
        slot_key="goal.p",
        category="goal",
        statement="长期项目",
        normalized_value_hash="hx",
        origin="inferred",
        status="confirmed",
    )
    mem.set_last_seen_at(fact["id"], _old_ts(95))
    mem.add_evidence(
        fact_id=fact["id"],
        conversation_id=cid,
        message_id="m1",
        start_char=0,
        end_char=4,
        quote_hash="q",
    )
    job = MemoryMaintenanceJob(mem, conv)
    out = job.run()
    assert out["changed"] == 1
    assert mem.get_fact(fact["id"])["status"] == "stale"
    events = conv.list_system_events(cid)
    assert events
    assert events[0]["payload"]["type"] == "memory_decayed"


def test_maintenance_never_deletes_rows(tmp_path):
    mem = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    fact = mem.upsert_fact(
        slot_key="goal.p",
        category="goal",
        statement="长期项目",
        normalized_value_hash="hx",
        origin="inferred",
        status="confirmed",
    )
    mem.set_last_seen_at(fact["id"], _old_ts(95))
    MemoryMaintenanceJob(mem).run()
    row = mem.get_fact(fact["id"])
    assert row is not None
    assert row["statement"] == "长期项目"
