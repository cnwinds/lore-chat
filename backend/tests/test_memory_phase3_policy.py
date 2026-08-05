from app.engine.memory.observer import MemoryObserver
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.engine.conversations import ConversationStore
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


def _observer(tmp_path):
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    return MemoryObserver(store), store


def _conv_store(tmp_path):
    return ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")


def test_direct_self_statement_confirms_immediately(tmp_path):
    observer, mem = _observer(tmp_path)
    out = observer.observe_message(
        "我偏好简洁回答",
        conversation_id="c1",
        message_id="m1",
    )
    assert out.confirmed_count == 1
    assert mem.list_confirmed()


def test_inferred_same_session_stays_candidate(tmp_path):
    observer, mem = _observer(tmp_path)
    text = "看来我可能喜欢简洁回答"
    observer.observe_message(text, conversation_id="c1", message_id="m1")
    observer.observe_message(text, conversation_id="c1", message_id="m2")
    assert mem.list_confirmed() == []
    assert len(mem.list_candidates()) == 1


def test_inferred_promotes_after_two_sessions(tmp_path):
    observer, mem = _observer(tmp_path)
    text = "看来我可能喜欢简洁回答"
    observer.observe_message(text, conversation_id="c1", message_id="m1")
    observer.observe_message(text, conversation_id="c2", message_id="m2")
    confirmed = mem.list_confirmed()
    assert len(confirmed) == 1
    assert confirmed[0]["origin"] == "inferred"


def test_sensitive_without_auth_not_saved(tmp_path):
    observer, mem = _observer(tmp_path)
    out = observer.observe_message(
        "我住在北京市朝阳区某某路100号",
        conversation_id="c1",
        message_id="m1",
    )
    assert out.confirmed_count == 0
    assert mem.list_confirmed() == []
    assert mem.list_candidates() == []


def test_conflict_supersedes_inferred(tmp_path):
    from app.engine.memory.normalize import normalize_slot_key, value_hash

    observer, mem = _observer(tmp_path)
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
    observer.observe_message(direct_stmt, conversation_id="c1", message_id="m1")
    old_fact = mem.get_fact(old["id"])
    assert old_fact["status"] == "superseded"
    confirmed = mem.list_confirmed()
    assert any("冗长" in f["statement"] for f in confirmed)


def test_candidate_never_in_recall(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    svc = MemoryService(store, repo, knowledge_writer=make_writer(repo, tmp_path))
    observer = MemoryObserver(store)
    observer.observe_message(
        "看来我可能喜欢喝茶",
        conversation_id="c1",
        message_id="m1",
    )
    out = svc.recall("喝茶")
    assert out["count"] == 0
