from app.engine.memory.policy import (
    allows_automatic_save,
    infer_sensitivity,
    initial_status,
)
from app.engine.memory.resolver import SlotAction, SlotResolver
from app.engine.memory.store import MemoryStore


def test_initial_status_by_origin():
    assert initial_status("direct", "随便写") == "confirmed"
    assert initial_status("manual") == "confirmed"
    assert initial_status("explicit_remember") == "confirmed"
    assert initial_status("inferred", "推断句") == "candidate"


def test_resolver_rejects_sensitive_without_auth(tmp_path):
    """敏感门槛由 SlotResolver + policy 覆盖。"""
    store = MemoryStore(tmp_path / "memory.db", owner_key="test")
    resolver = SlotResolver(store)
    out = resolver.apply(
        SlotAction(
            slot_key="identity.address",
            action="new",
            statement="我住在北京市朝阳区某某路100号",
            category="identity",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    assert out["ok"] is False
    assert out.get("error") == "rejected"
    assert store.list_confirmed() == []
    assert store.list_candidates() == []


def test_sensitive_manual_allowed():
    assert infer_sensitivity("我住在北京市朝阳区某某路100号") == "sensitive"
    assert allows_automatic_save("sensitive", "manual")
    assert not allows_automatic_save("sensitive", "direct")
