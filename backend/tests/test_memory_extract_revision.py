from datetime import datetime, timedelta, timezone

from app.engine.conversations import ConversationStore
from app.engine.memory.service import MemoryService
from app.engine.memory.session_extractor import RuleBasedSessionExtractor
from app.engine.memory.store import MemoryStore
from app.engine.memory_worker import MemoryWorker
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


def test_clear_memory_dirty_increments_extract_revision(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    assert store.get_memory_extract_revision(cid) == 0
    store.mark_memory_dirty(cid)
    rev1 = store.clear_memory_dirty(cid)
    rev2 = store.clear_memory_dirty(cid)
    assert rev1 == 1
    assert rev2 == 2
    assert store.get_memory_extract_revision(cid) == 2


def test_enqueue_session_observe_after_done_uses_new_revision(tmp_path):
    """首轮 done 后二次入队不得撞唯一键。"""
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    store.begin_turn(cid, "我偏好简洁回答", "c1", observation_allowed=True)
    assert store.enqueue_session_observe(cid) is True
    jobs = store.claim_outbox(kind="session_observe_memory", limit=1, lease_seconds=60)
    assert len(jobs) == 1
    store.complete_outbox(jobs[0]["id"])
    assert store.enqueue_session_observe(cid) is True
    pending = [
        j
        for j in store.list_outbox(kind="session_observe_memory")
        if j["status"] == "pending"
    ]
    assert len(pending) == 1
    assert int(pending[0]["source_revision"]) >= 2


def test_session_worker_bumps_revision_on_success(tmp_path):
    conv = ConversationStore(tmp_path / "conversations")
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    mem = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    svc = MemoryService(mem, repo, knowledge_writer=make_writer(repo, tmp_path))
    worker = MemoryWorker(
        conv, svc, extractor=RuleBasedSessionExtractor(), idle_hours=0
    )
    cid = conv.create()
    conv.begin_turn(cid, "我偏好简洁回答", "c1", observation_allowed=True)
    past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    conv.conn.execute(
        "UPDATE conversations SET last_user_message_at = ? WHERE id = ?",
        (past, cid),
    )
    conv.conn.commit()
    assert conv.get_memory_extract_revision(cid) == 0
    worker.drain(max_jobs=5)
    assert conv.get_memory_extract_revision(cid) >= 1
