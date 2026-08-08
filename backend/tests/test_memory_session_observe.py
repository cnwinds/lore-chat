from datetime import datetime, timedelta, timezone

from app.engine.conversations import ConversationStore
from app.engine.memory.resolver import SlotAction
from app.engine.memory.service import MemoryService
from app.engine.memory.session_extractor import RuleBasedSessionExtractor
from app.engine.memory.store import MemoryStore
from app.engine.memory_worker import MemoryWorker
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


def test_begin_turn_marks_memory_dirty_without_per_message_observe(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    turn = store.begin_turn(
        cid, "我偏好用数据可视化替代插图", "c1", observation_allowed=True
    )
    assert store.list_outbox(kind="observe_memory") == []
    row = store.conn.execute(
        "SELECT memory_dirty, last_user_message_at FROM conversations WHERE id = ?",
        (cid,),
    ).fetchone()
    assert row["memory_dirty"] == 1
    assert row["last_user_message_at"]
    assert turn["user_message"]["id"]


def test_session_worker_merges_visualization_preference(tmp_path):
    conv = ConversationStore(tmp_path / "conversations")
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    mem = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    svc = MemoryService(mem, repo, knowledge_writer=make_writer(repo, tmp_path))
    worker = MemoryWorker(
        conv, svc, extractor=RuleBasedSessionExtractor(), idle_hours=0
    )

    cid = conv.create()
    conv.begin_turn(
        cid,
        "我偏好只用数据可视化元素（如榜单、词云、分布图）来替代插图，而不是使用AI生成的图片。",
        "c1",
        observation_allowed=True,
    )
    # 模拟已空闲：把 last_user_message_at 拨到过去
    past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    conv.conn.execute(
        "UPDATE conversations SET last_user_message_at = ? WHERE id = ?",
        (past, cid),
    )
    conv.conn.commit()

    n = worker.drain(max_jobs=5)
    assert n >= 1
    confirmed = mem.list_confirmed()
    assert len(confirmed) == 1
    assert confirmed[0]["slot_key"] == "preference.illustration_style"

    # 第二会话近义表述 → merge 仍一条
    cid2 = conv.create()
    conv.begin_turn(
        cid2,
        "我偏好用数据可视化（如榜单、词云等）替代插图。",
        "c2",
        observation_allowed=True,
    )
    conv.conn.execute(
        "UPDATE conversations SET last_user_message_at = ? WHERE id = ?",
        (past, cid2),
    )
    conv.conn.commit()
    worker.drain(max_jobs=5)
    confirmed = mem.list_confirmed()
    assert len(confirmed) == 1
    assert confirmed[0]["slot_key"] == "preference.illustration_style"


def test_mark_summarized_enqueues_immediate_session_observe(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    store.begin_turn(cid, "我偏好简洁回答", "c1", observation_allowed=True)
    store.mark_summarized(cid, "归档/测试.md")
    jobs = [
        j
        for j in store.list_outbox(kind="session_observe_memory")
        if j["status"] == "pending"
    ]
    assert len(jobs) == 1
    assert jobs[0]["source_message_id"] == f"conv:{cid}"
    from app.engine.conversation.outbox import SESSION_OBSERVE_IMMEDIATE

    assert jobs[0]["turn_id"] == SESSION_OBSERVE_IMMEDIATE
    row = store.conn.execute(
        "SELECT memory_dirty FROM conversations WHERE id = ?", (cid,)
    ).fetchone()
    assert row["memory_dirty"] == 1


def test_continue_chat_cancels_pending_session_observe(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    turn = store.begin_turn(cid, "我偏好简洁回答", "c1", observation_allowed=True)
    store.finalize_turn(
        cid,
        turn["turn_id"],
        assistant={"text": "好", "timeline": [], "sources": [], "status": "complete"},
    )
    assert store.enqueue_session_observe(cid) is True
    pending = [
        j
        for j in store.list_outbox(kind="session_observe_memory")
        if j["status"] == "pending"
    ]
    assert len(pending) == 1
    store.begin_turn(cid, "再补充一句", "c2", observation_allowed=True)
    pending_after = [
        j
        for j in store.list_outbox(kind="session_observe_memory")
        if j["status"] == "pending"
    ]
    assert pending_after == []


def test_archive_during_running_requeues_immediate(tmp_path):
    """抽取进行中归档：CAS 保留 dirty，结束后再入队 immediate。"""
    from app.engine.conversation.outbox import SESSION_OBSERVE_IMMEDIATE

    conv = ConversationStore(tmp_path / "conversations")
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    mem = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    svc = MemoryService(mem, repo, knowledge_writer=make_writer(repo, tmp_path))
    inner = RuleBasedSessionExtractor()

    class _ArchiveMidExtract:
        """在快照之后、定稿之前触发归档即时请求。"""

        def extract(self, user_texts, confirmed_summary=None):
            with conv._lock:
                ok = conv._request_immediate_memory_extract_unlocked(
                    cid, at="2099-01-01T00:00:00+00:00"
                )
                conv.conn.commit()
            assert ok is False
            return inner.extract(user_texts, confirmed_summary=confirmed_summary)

    worker = MemoryWorker(conv, svc, extractor=_ArchiveMidExtract(), idle_hours=24)
    cid = conv.create()
    conv.begin_turn(cid, "我偏好简洁回答", "c1", observation_allowed=True)
    assert conv.enqueue_session_observe(cid, immediate=True) is True
    jobs = conv.claim_outbox(kind="session_observe_memory", limit=1, lease_seconds=120)
    assert len(jobs) == 1
    worker.process_session_job(jobs[0])
    dirty = conv.conn.execute(
        "SELECT memory_dirty, memory_immediate_pending FROM conversations WHERE id = ?",
        (cid,),
    ).fetchone()
    assert dirty["memory_dirty"] == 1
    assert dirty["memory_immediate_pending"] == 0
    follow = [
        j
        for j in conv.list_outbox(kind="session_observe_memory")
        if j["status"] == "pending"
    ]
    assert len(follow) == 1
    assert follow[0]["turn_id"] == SESSION_OBSERVE_IMMEDIATE


def test_clear_dirty_cas_keeps_dirty_after_mid_extract_chat(tmp_path):
    """running 抽取期间续聊：结束后不得清掉新的 dirty。"""
    conv = ConversationStore(tmp_path / "conversations")
    cid = conv.create()
    conv.begin_turn(cid, "我偏好简洁回答", "c1", observation_allowed=True)
    snap = conv.get_last_user_message_at(cid)
    # 模拟续聊：显式推进 last_user_message_at
    newer = "2099-01-01T00:00:00+00:00"
    conv.mark_memory_dirty(cid, at=newer)
    assert conv.get_last_user_message_at(cid) == newer
    assert (
        conv.clear_memory_dirty(cid, expected_last_user_message_at=snap) is None
    )
    row = conv.conn.execute(
        "SELECT memory_dirty FROM conversations WHERE id = ?", (cid,)
    ).fetchone()
    assert row["memory_dirty"] == 1
    rev = conv.clear_memory_dirty(cid, expected_last_user_message_at=newer)
    assert rev is not None and rev >= 1


def test_worker_skips_extract_when_not_idle(tmp_path):
    """非即时任务：消费时未空闲则不抽取、不清 dirty。"""
    conv = ConversationStore(tmp_path / "conversations")
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    mem = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    svc = MemoryService(mem, repo, knowledge_writer=make_writer(repo, tmp_path))
    worker = MemoryWorker(
        conv, svc, extractor=RuleBasedSessionExtractor(), idle_hours=24
    )
    cid = conv.create()
    conv.begin_turn(cid, "我偏好简洁回答", "c1", observation_allowed=True)
    assert conv.enqueue_session_observe(cid) is True
    # last_user_message_at 刚写入 → 未满 24h
    n = worker.drain(max_jobs=5)
    assert n >= 1
    assert mem.list_confirmed() == []
    row = conv.conn.execute(
        "SELECT memory_dirty FROM conversations WHERE id = ?", (cid,)
    ).fetchone()
    assert row["memory_dirty"] == 1


def test_noop_promote_updates_db_context(tmp_path):
    """noop 路径晋升为 confirmed 后，DB 直出上下文须可见。"""
    conv = ConversationStore(tmp_path / "conversations")
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    mem = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    svc = MemoryService(mem, repo, knowledge_writer=make_writer(repo, tmp_path))
    from app.engine.memory.normalize import value_hash

    stmt = "我似乎偏好简洁回答"
    fact = mem.upsert_fact(
        slot_key="preference.response_style",
        category="preference",
        statement=stmt,
        normalized_value_hash=value_hash(stmt),
        origin="inferred",
        confidence=0.85,
        status="candidate",
    )
    mem.add_session_evidence(fact["id"], "c-prior")

    class NoopExtractor:
        def extract(self, user_messages, *, confirmed_summary):
            return [
                SlotAction(
                    slot_key="preference.response_style",
                    action="noop",
                    statement=stmt,
                    category="preference",
                    origin="inferred",
                    confidence=0.85,
                )
            ]

    worker = MemoryWorker(conv, svc, extractor=NoopExtractor(), idle_hours=0)
    cid = conv.create()
    conv.begin_turn(cid, "还是简洁点吧", "c1", observation_allowed=True)
    past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    conv.conn.execute(
        "UPDATE conversations SET last_user_message_at = ? WHERE id = ?",
        (past, cid),
    )
    conv.conn.commit()
    worker.drain(max_jobs=5)
    assert mem.list_confirmed()
    assert "简洁" in svc.render_context()
    assert not repo.abs_path("系统/记忆.md").exists()
    row = conv.conn.execute(
        "SELECT memory_dirty FROM conversations WHERE id = ?", (cid,)
    ).fetchone()
    assert row["memory_dirty"] == 0


def test_failed_apply_keeps_memory_dirty(tmp_path):
    class BoomExtractor:
        def extract(self, user_messages, *, confirmed_summary):
            return [
                SlotAction(
                    slot_key="preference.illustration_style",
                    action="new",
                    statement="",  # empty → resolver reject
                    category="preference",
                    origin="direct",
                )
            ]

    conv = ConversationStore(tmp_path / "conversations")
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    mem = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    svc = MemoryService(mem, repo, knowledge_writer=make_writer(repo, tmp_path))
    worker = MemoryWorker(conv, svc, extractor=BoomExtractor(), idle_hours=0)
    cid = conv.create()
    conv.begin_turn(cid, "hello", "c1", observation_allowed=True)
    past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    conv.conn.execute(
        "UPDATE conversations SET last_user_message_at = ? WHERE id = ?",
        (past, cid),
    )
    conv.conn.commit()
    worker.drain(max_jobs=5)
    row = conv.conn.execute(
        "SELECT memory_dirty FROM conversations WHERE id = ?", (cid,)
    ).fetchone()
    assert row["memory_dirty"] == 1


def test_partial_failure_still_keeps_confirmed_in_context(tmp_path):
    """同批有成功 confirmed 与失败项时，成功项进入 DB 直出上下文，并保留 dirty。"""

    class MixedExtractor:
        def extract(self, user_messages, *, confirmed_summary):
            return [
                SlotAction(
                    slot_key="preference.response_style",
                    action="new",
                    statement="我偏好简洁回答",
                    category="preference",
                    origin="direct",
                    confidence=0.9,
                ),
                SlotAction(
                    slot_key="preference.illustration_style",
                    action="new",
                    statement="",
                    category="preference",
                    origin="direct",
                ),
            ]

    conv = ConversationStore(tmp_path / "conversations")
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    mem = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    svc = MemoryService(mem, repo, knowledge_writer=make_writer(repo, tmp_path))
    worker = MemoryWorker(conv, svc, extractor=MixedExtractor(), idle_hours=0)
    cid = conv.create()
    conv.begin_turn(cid, "混合", "c1", observation_allowed=True)
    past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    conv.conn.execute(
        "UPDATE conversations SET last_user_message_at = ? WHERE id = ?",
        (past, cid),
    )
    conv.conn.commit()
    worker.drain(max_jobs=5)
    assert any("简洁" in f["statement"] for f in mem.list_confirmed())
    assert "简洁" in svc.render_context()
    row = conv.conn.execute(
        "SELECT memory_dirty FROM conversations WHERE id = ?", (cid,)
    ).fetchone()
    assert row["memory_dirty"] == 1

