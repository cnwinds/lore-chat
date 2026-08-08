"""supersede 后出处须迁到存活 fact，否则面板跳转 conversation_ids 为空。"""

from app.engine.memory.normalize import value_hash
from app.engine.memory.resolver import SlotAction, SlotResolver
from app.engine.memory.store import MemoryStore


def test_mark_superseded_rebinds_evidence(tmp_path):
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    old = store.upsert_fact(
        slot_key="preference.old_slot",
        category="preference",
        statement="我偏好旧表述",
        normalized_value_hash=value_hash("我偏好旧表述"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    store.add_session_evidence(old["id"], "conv-src")
    new = store.upsert_fact(
        slot_key="preference.new_slot",
        category="preference",
        statement="我偏好新表述",
        normalized_value_hash=value_hash("我偏好新表述"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    store.mark_superseded(old["id"], supersedes_id=new["id"])
    assert store.list_evidence(old["id"]) == []
    cids = {e["conversation_id"] for e in store.list_evidence(new["id"])}
    assert "conv-src" in cids


def test_resolver_create_confirmed_rebinds_prior_same_slot_evidence(tmp_path):
    """同槽：先 stale/旧 confirmed，再 new 不同 hash → 出处跟到新 keep。"""
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    r1 = resolver.apply(
        SlotAction(
            slot_key="goal.active_project",
            action="new",
            statement="我长期做教育科技方向",
            category="goal",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    assert r1["ok"]
    old_id = r1["fact"]["id"]
    store.set_status(old_id, "stale")

    r2 = resolver.apply(
        SlotAction(
            slot_key="goal.active_project",
            action="new",
            statement="我长期做开源工具平台",
            category="goal",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c2",
    )
    assert r2["ok"]
    # stale 被选为 primary 后走 merge 就地更新，或新建后 supersede；出处应在存活条
    keep = store.list_confirmed()
    assert len(keep) == 1
    cids = {e["conversation_id"] for e in store.list_evidence(keep[0]["id"])}
    assert "c1" in cids
    assert "c2" in cids
    assert store.get_fact(old_id)["status"] in ("confirmed", "superseded")


def test_repair_evidence_following_supersede(tmp_path):
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    old = store.upsert_fact(
        slot_key="a",
        category="preference",
        statement="旧",
        normalized_value_hash=value_hash("旧"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    store.add_session_evidence(old["id"], "conv-z")
    new = store.upsert_fact(
        slot_key="b",
        category="preference",
        statement="新",
        normalized_value_hash=value_hash("新"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    # 模拟旧 bug：只改 status/supersedes_id，不迁 evidence
    with store._connect() as conn:
        conn.execute(
            """
            UPDATE memory_facts SET status = 'superseded', supersedes_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (new["id"], "2026-01-01T00:00:00+00:00", old["id"]),
        )
        conn.commit()
    assert store.list_evidence(new["id"]) == []
    assert store.repair_evidence_following_supersede() >= 1
    assert "conv-z" in {e["conversation_id"] for e in store.list_evidence(new["id"])}


def test_repair_skips_dangling_supersedes_id(tmp_path):
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    old = store.upsert_fact(
        slot_key="a",
        category="preference",
        statement="旧",
        normalized_value_hash=value_hash("旧"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    store.add_session_evidence(old["id"], "conv-dangle")
    good_old = store.upsert_fact(
        slot_key="x",
        category="preference",
        statement="可修旧",
        normalized_value_hash=value_hash("可修旧"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    store.add_session_evidence(good_old["id"], "conv-ok")
    good_new = store.upsert_fact(
        slot_key="y",
        category="preference",
        statement="可修新",
        normalized_value_hash=value_hash("可修新"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    with store._connect() as conn:
        conn.execute(
            """
            UPDATE memory_facts SET status = 'superseded', supersedes_id = ?, updated_at = ?
            WHERE id = ?
            """,
            ("missing-fact-id", "2026-01-01T00:00:00+00:00", old["id"]),
        )
        conn.execute(
            """
            UPDATE memory_facts SET status = 'superseded', supersedes_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (good_new["id"], "2026-01-01T00:00:00+00:00", good_old["id"]),
        )
        conn.commit()
    # 不得因悬空 id 抛错，且其它行仍能修
    n = store.repair_evidence_following_supersede()
    assert n >= 1
    assert "conv-ok" in {e["conversation_id"] for e in store.list_evidence(good_new["id"])}
    # 悬空目标：evidence 仍留在 old（无法安全迁移）
    assert "conv-dangle" in {e["conversation_id"] for e in store.list_evidence(old["id"])}


def test_update_fact_content_frees_hash_held_by_stale(tmp_path):
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    stale = store.upsert_fact(
        slot_key="preference.style",
        category="preference",
        statement="旧句",
        normalized_value_hash=value_hash("旧句"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    store.set_status(stale["id"], "stale")
    keep = store.upsert_fact(
        slot_key="preference.style",
        category="preference",
        statement="新句",
        normalized_value_hash=value_hash("新句"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    # 把 keep 改写成 stale 原文/hash，不得 IntegrityError
    updated = store.update_fact_content(
        keep["id"],
        statement="旧句",
        normalized_value_hash=value_hash("旧句"),
        status="confirmed",
    )
    assert updated["statement"] == "旧句"
    assert store.get_fact(stale["id"])["normalized_value_hash"] != value_hash("旧句")


def test_repair_follows_supersede_chain(tmp_path):
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    a = store.upsert_fact(
        slot_key="a",
        category="preference",
        statement="A",
        normalized_value_hash=value_hash("A"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    store.add_session_evidence(a["id"], "conv-a")
    b = store.upsert_fact(
        slot_key="b",
        category="preference",
        statement="B",
        normalized_value_hash=value_hash("B"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    c = store.upsert_fact(
        slot_key="c",
        category="preference",
        statement="C",
        normalized_value_hash=value_hash("C"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    with store._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET status='superseded', supersedes_id=? WHERE id=?",
            (b["id"], a["id"]),
        )
        conn.execute(
            "UPDATE memory_facts SET status='superseded', supersedes_id=? WHERE id=?",
            (c["id"], b["id"]),
        )
        conn.commit()
    store.repair_evidence_following_supersede()
    assert "conv-a" in {e["conversation_id"] for e in store.list_evidence(c["id"])}
