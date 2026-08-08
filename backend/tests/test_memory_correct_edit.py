from app.engine.memory.normalize import value_hash
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


def _svc(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    return MemoryService(store, repo, knowledge_writer=make_writer(repo, tmp_path)), store


def test_correct_keeps_old_when_remember_fails(tmp_path):
    svc, store = _svc(tmp_path)
    old = store.upsert_fact(
        slot_key="preference.pet",
        category="preference",
        statement="我喜欢养狗",
        normalized_value_hash=value_hash("我喜欢养狗"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    out = svc.correct(
        fact_id=old["id"],
        replacement="key=sk-abcdefghijklmnopqrstuvwxyz012345",
    )
    assert not out.get("ok")
    assert store.get_fact(old["id"])["status"] == "confirmed"


def test_correct_forgets_old_only_after_success(tmp_path):
    svc, store = _svc(tmp_path)
    old = store.upsert_fact(
        slot_key="preference.pet",
        category="preference",
        statement="我喜欢养狗",
        normalized_value_hash=value_hash("我喜欢养狗"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    store.add_session_evidence(old["id"], "conv-pet")
    out = svc.correct(fact_id=old["id"], replacement="我喜欢养猫")
    assert out.get("ok")
    confirmed = store.list_confirmed()
    assert len(confirmed) == 1
    assert confirmed[0]["id"] == old["id"]
    assert confirmed[0]["slot_key"] == "preference.pet"
    assert "养猫" in confirmed[0]["statement"]
    assert "conv-pet" in {
        e["conversation_id"] for e in store.list_evidence(confirmed[0]["id"])
    }
    assert store.has_tombstone(
        slot_key="preference.pet",
        normalized_value_hash=value_hash("我喜欢养狗"),
    )


def test_correct_updates_target_fact_not_slot_primary(tmp_path):
    svc, store = _svc(tmp_path)
    older = store.upsert_fact(
        slot_key="preference.pet",
        category="preference",
        statement="我喜欢养狗",
        normalized_value_hash=value_hash("我喜欢养狗"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    newer = store.upsert_fact(
        slot_key="preference.pet",
        category="preference",
        statement="我喜欢养鱼",
        normalized_value_hash=value_hash("我喜欢养鱼"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    # 更正较旧的那条，不得把 newer 的语句改掉
    out = svc.correct(fact_id=older["id"], replacement="我喜欢养猫")
    assert out.get("ok")
    assert "养猫" in store.get_fact(older["id"])["statement"]
    assert store.get_fact(older["id"])["status"] == "confirmed"
    assert store.get_fact(newer["id"])["status"] == "superseded"


def test_edit_fact_supersedes_parallel_slot_mates(tmp_path):
    svc, store = _svc(tmp_path)
    a = store.upsert_fact(
        slot_key="preference.pet",
        category="preference",
        statement="我喜欢猫",
        normalized_value_hash=value_hash("我喜欢猫"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    b = store.upsert_fact(
        slot_key="preference.pet",
        category="preference",
        statement="我喜欢狗",
        normalized_value_hash=value_hash("我喜欢狗"),
        origin="inferred",
        confidence=0.8,
        status="candidate",
    )
    out = svc.edit_fact(b["id"], "我喜欢猫")
    assert out.get("ok")
    assert store.get_fact(a["id"])["status"] == "superseded"
    assert store.get_fact(b["id"])["status"] == "candidate"
    panel = svc.list_panel_facts()["facts"]
    active = [f for f in panel if f["id"] in (a["id"], b["id"])]
    assert len(active) == 1
    assert store.has_tombstone(
        slot_key="preference.pet",
        normalized_value_hash=value_hash("我喜欢狗"),
    )


def test_edit_to_existing_statement_supersedes_duplicate(tmp_path):
    """编辑成另一条已存活同句时，须灭活重复条，不得双 confirmed。"""
    svc, store = _svc(tmp_path)
    shared = "我偏好简洁回答"
    a = store.upsert_fact(
        slot_key="preference.response_style",
        category="preference",
        statement=shared,
        normalized_value_hash=value_hash(shared),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    b = store.upsert_fact(
        slot_key="preference.pet",
        category="preference",
        statement="我喜欢养狗",
        normalized_value_hash=value_hash("我喜欢养狗"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    out = svc.edit_fact(b["id"], shared)
    assert out.get("ok")
    assert store.get_fact(a["id"])["status"] == "superseded"
    assert store.get_fact(b["id"])["status"] in ("confirmed", "candidate")
    assert len(store.list_confirmed()) == 1
    assert store.list_confirmed()[0]["id"] == b["id"]


def test_edit_topic_slot_migrates_with_statement(tmp_path):
    """topic_* 嵌入内容指纹：改句后必须迁槽，否则再抽取会平行开第二条。"""
    svc, store = _svc(tmp_path)
    old_stmt = "我周末常去爬山"
    new_stmt = "我周末常去游泳"
    old_slot = f"preference.topic_{value_hash(old_stmt)[:12]}"
    new_slot = f"preference.topic_{value_hash(new_stmt)[:12]}"
    assert old_slot != new_slot
    fact = store.upsert_fact(
        slot_key=old_slot,
        category="preference",
        statement=old_stmt,
        normalized_value_hash=value_hash(old_stmt),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    out = svc.edit_fact(fact["id"], new_stmt)
    assert out.get("ok")
    updated = store.get_fact(fact["id"])
    assert updated["slot_key"] == new_slot
    assert updated["statement"] == new_stmt
    assert store.has_tombstone(
        slot_key=old_slot, normalized_value_hash=value_hash(old_stmt)
    )


def test_correct_topic_slot_migrates_with_statement(tmp_path):
    svc, store = _svc(tmp_path)
    old_stmt = "我偏好晨跑"
    new_stmt = "我偏好夜跑"
    old_slot = f"preference.topic_{value_hash(old_stmt)[:12]}"
    new_slot = f"preference.topic_{value_hash(new_stmt)[:12]}"
    fact = store.upsert_fact(
        slot_key=old_slot,
        category="preference",
        statement=old_stmt,
        normalized_value_hash=value_hash(old_stmt),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    out = svc.correct(fact_id=fact["id"], replacement=new_stmt)
    assert out.get("ok")
    updated = store.get_fact(fact["id"])
    assert updated["slot_key"] == new_slot
    assert "夜跑" in updated["statement"]


def test_edit_fact_clears_tombstone_for_rewritten_value(tmp_path):
    """用户编辑写回曾遗忘的值时，须清 tombstone（与 correct 对齐）。"""
    svc, store = _svc(tmp_path)
    revived = "我喜欢喝茶"
    fact = store.upsert_fact(
        slot_key="preference.drink",
        category="preference",
        statement="我喜欢喝咖啡",
        normalized_value_hash=value_hash("我喜欢喝咖啡"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    store.block_value(
        slot_key="preference.drink",
        normalized_value_hash=value_hash(revived),
        reason="forgotten",
    )
    out = svc.edit_fact(fact["id"], revived)
    assert out.get("ok")
    assert not store.has_tombstone(
        slot_key="preference.drink",
        normalized_value_hash=value_hash(revived),
    )
    assert store.get_fact(fact["id"])["statement"] == revived
