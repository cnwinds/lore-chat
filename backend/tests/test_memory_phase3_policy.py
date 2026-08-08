from app.engine.memory.normalize import normalize_slot_key, value_hash
from app.engine.memory.policy import allows_automatic_save, infer_sensitivity
from app.engine.memory.resolver import SlotAction, SlotResolver
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


def _resolver(tmp_path):
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    return SlotResolver(store), store


def test_direct_self_statement_confirms_immediately(tmp_path):
    resolver, mem = _resolver(tmp_path)
    out = resolver.apply(
        SlotAction(
            slot_key="preference.response_style",
            action="new",
            statement="我偏好简洁回答",
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    assert out["ok"]
    assert out["fact"]["status"] == "confirmed"
    assert mem.list_confirmed()


def test_explicit_remember_confirms_immediately(tmp_path):
    resolver, mem = _resolver(tmp_path)
    out = resolver.apply(
        SlotAction(
            slot_key="preference.response_style",
            action="new",
            statement="请记住我偏好简洁回答",
            category="preference",
            origin="explicit_remember",
            confidence=1.0,
        ),
        conversation_id="c1",
    )
    assert out["ok"]
    assert out["fact"]["status"] == "confirmed"
    assert mem.list_confirmed()


def test_inferred_same_session_stays_candidate(tmp_path):
    resolver, mem = _resolver(tmp_path)
    action = SlotAction(
        slot_key="preference.response_style",
        action="new",
        statement="我似乎偏好简洁回答",
        category="preference",
        origin="inferred",
        confidence=0.85,
    )
    resolver.apply(action, conversation_id="c1")
    resolver.apply(action, conversation_id="c1")
    assert mem.list_confirmed() == []
    assert len(mem.list_candidates()) == 1


def test_inferred_promotes_after_two_sessions(tmp_path):
    resolver, mem = _resolver(tmp_path)
    action = SlotAction(
        slot_key="preference.response_style",
        action="new",
        statement="我似乎偏好简洁回答",
        category="preference",
        origin="inferred",
        confidence=0.85,
    )
    resolver.apply(action, conversation_id="c1")
    resolver.apply(action, conversation_id="c2")
    confirmed = mem.list_confirmed()
    assert len(confirmed) == 1
    assert confirmed[0]["origin"] == "inferred"
    assert mem.count_distinct_conversation_evidence(confirmed[0]["id"]) == 2


def test_sensitive_without_auth_not_saved(tmp_path):
    resolver, mem = _resolver(tmp_path)
    statement = "我住在北京市朝阳区某某路100号"
    assert infer_sensitivity(statement) == "sensitive"
    assert not allows_automatic_save("sensitive", "direct")
    out = resolver.apply(
        SlotAction(
            slot_key="identity.address",
            action="new",
            statement=statement,
            category="identity",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    assert out["ok"] is False
    assert out.get("error") == "rejected"
    assert mem.list_confirmed() == []
    assert mem.list_candidates() == []


def test_conflict_supersedes_inferred(tmp_path):
    resolver, mem = _resolver(tmp_path)
    direct_stmt = "我偏好冗长回答"
    slot = normalize_slot_key("preference", direct_stmt)
    old = mem.upsert_fact(
        slot_key=slot,
        category="preference",
        statement="我偏好简洁回答",
        normalized_value_hash=value_hash("我偏好简洁回答"),
        origin="inferred",
        confidence=0.9,
        status="confirmed",
    )
    out = resolver.apply(
        SlotAction(
            slot_key=slot,
            action="replace",
            statement=direct_stmt,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    assert out["ok"]
    confirmed = mem.list_confirmed()
    assert len(confirmed) == 1
    assert any("冗长" in f["statement"] for f in confirmed)
    assert confirmed[0]["origin"] == "direct"
    assert not any("简洁" in f["statement"] for f in confirmed)
    # SlotResolver 就地改写 primary；若另有同槽存活条则应被 supersede
    old_fact = mem.get_fact(old["id"])
    assert old_fact is None or old_fact["status"] in ("confirmed", "superseded")
    if old_fact and old_fact["status"] == "confirmed":
        assert "冗长" in old_fact["statement"]


def test_candidate_never_in_recall(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    svc = MemoryService(store, repo, knowledge_writer=make_writer(repo, tmp_path))
    resolver = SlotResolver(store)
    resolver.apply(
        SlotAction(
            slot_key="preference.drink",
            action="new",
            statement="我似乎喜欢喝茶",
            category="preference",
            origin="inferred",
            confidence=0.85,
        ),
        conversation_id="c1",
    )
    assert store.list_candidates()
    out = svc.recall("喝茶")
    assert out["count"] == 0
