"""Phase 4: per-category decay rules."""

from datetime import datetime, timedelta, timezone

from app.engine.memory.decay import DecayConfig, decay_target_status, is_decay_exempt
from app.engine.memory.store import MemoryStore


def _store(tmp_path):
    return MemoryStore(tmp_path / "memory.db", owner_key="ws1")


def _old_ts(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_manual_origin_never_decays(tmp_path):
    store = _store(tmp_path)
    fact = store.upsert_fact(
        slot_key="preference.manual",
        category="preference",
        statement="手动偏好",
        normalized_value_hash="h1",
        origin="manual",
        status="confirmed",
    )
    store.set_last_seen_at(fact["id"], _old_ts(200))
    updated = store.get_fact(fact["id"])
    target = decay_target_status(
        updated,
        now=datetime.now(timezone.utc),
        config=DecayConfig(),
    )
    assert target is None
    assert is_decay_exempt(fact)


def test_identity_never_decays(tmp_path):
    store = _store(tmp_path)
    fact = store.upsert_fact(
        slot_key="identity.me",
        category="identity",
        statement="我是工程师",
        normalized_value_hash="h2",
        origin="inferred",
        status="confirmed",
    )
    target = decay_target_status(
        {**fact, "last_seen_at": _old_ts(200)},
        now=datetime.now(timezone.utc),
        config=DecayConfig(),
    )
    assert target is None


def test_goal_becomes_stale_after_90_days(tmp_path):
    store = _store(tmp_path)
    fact = store.upsert_fact(
        slot_key="goal.proj",
        category="goal",
        statement="在做 side project",
        normalized_value_hash="h3",
        origin="inferred",
        status="confirmed",
    )
    target = decay_target_status(
        {**fact, "last_seen_at": _old_ts(91)},
        now=datetime.now(timezone.utc),
        config=DecayConfig(),
    )
    assert target == "stale"
