from app.engine.memory.normalize import value_hash
from app.engine.memory.resolver import SlotAction, SlotResolver
from app.engine.memory.store import MemoryStore


def test_merge_paraphrases_into_one_confirmed(tmp_path):
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    first = (
        "我偏好只用数据可视化元素（如榜单、词云、分布图）来替代插图，而不是使用AI生成的图片。"
    )
    second = "我偏好用数据可视化（如榜单、词云等）替代插图。"
    merged = (
        "我偏好用数据可视化（榜单/词云/分布图）替代插图，不使用 AI 生成图。"
    )
    r1 = resolver.apply(
        SlotAction(
            slot_key="preference.illustration_style",
            action="new",
            statement=first,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    assert r1["ok"]
    r2 = resolver.apply(
        SlotAction(
            slot_key="preference.illustration_style",
            action="merge",
            statement=merged,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c2",
    )
    assert r2["ok"]
    confirmed = store.list_confirmed()
    assert len(confirmed) == 1
    assert confirmed[0]["statement"] == merged
    assert confirmed[0]["slot_key"] == "preference.illustration_style"
    assert store.count_distinct_conversation_evidence(confirmed[0]["id"]) == 2


def test_replace_supersedes_old_value(tmp_path):
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    resolver.apply(
        SlotAction(
            slot_key="preference.response_language",
            action="new",
            statement="默认使用英文",
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    resolver.apply(
        SlotAction(
            slot_key="preference.response_language",
            action="replace",
            statement="默认使用中文",
            category="preference",
            origin="direct",
            confidence=0.95,
        ),
        conversation_id="c2",
    )
    confirmed = store.list_confirmed()
    assert len(confirmed) == 1
    assert confirmed[0]["statement"] == "默认使用中文"
    assert value_hash(confirmed[0]["statement"]) == value_hash("默认使用中文")


def test_inferred_stays_candidate_until_second_conversation(tmp_path):
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    a = SlotAction(
        slot_key="preference.response_style",
        action="new",
        statement="我似乎偏好简洁回答",
        category="preference",
        origin="inferred",
        confidence=0.85,
    )
    resolver.apply(a, conversation_id="c1")
    assert store.list_confirmed() == []
    assert len(store.list_candidates()) == 1
    resolver.apply(a, conversation_id="c2")
    assert len(store.list_confirmed()) == 1
    assert store.list_candidates() == []


def test_inferred_paraphrase_merges_into_same_candidate(tmp_path):
    """同槽近义第二会话不得平行开 candidate。"""
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    resolver.apply(
        SlotAction(
            slot_key="preference.response_style",
            action="new",
            statement="我似乎偏好简洁回答",
            category="preference",
            origin="inferred",
            confidence=0.85,
        ),
        conversation_id="c1",
    )
    resolver.apply(
        SlotAction(
            slot_key="preference.response_style",
            action="new",
            statement="我好像更喜欢简短直接的回答",
            category="preference",
            origin="inferred",
            confidence=0.85,
        ),
        conversation_id="c2",
    )
    assert len(store.list_candidates()) + len(store.list_confirmed()) == 1
    assert len(store.list_confirmed()) == 1
    assert store.list_candidates() == []


def test_noop_refreshes_last_seen_same_conversation(tmp_path):
    """同会话 noop：不重复计会话数，但须刷新 last_seen（衰减依赖）。"""
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    r1 = resolver.apply(
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
    assert r1["ok"]
    fid = r1["fact"]["id"]
    store.set_last_seen_at(fid, "2000-01-01T00:00:00+00:00")
    before = store.get_fact(fid)["last_seen_at"]
    r2 = resolver.apply(
        SlotAction(
            slot_key="preference.response_style",
            action="noop",
            statement="我偏好简洁回答",
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    assert r2["ok"]
    after = store.get_fact(fid)["last_seen_at"]
    assert after != before
    assert after > before
    assert store.count_distinct_conversation_evidence(fid) == 1


def test_stale_primary_merge_inferred_revives_to_candidate(tmp_path):
    """stale + inferred merge 不得仍停留在 stale（否则画像不可见）。"""
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    r1 = resolver.apply(
        SlotAction(
            slot_key="goal.active_project",
            action="new",
            statement="我长期做教育科技",
            category="goal",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    fid = r1["fact"]["id"]
    store.set_status(fid, "stale")
    r2 = resolver.apply(
        SlotAction(
            slot_key="goal.active_project",
            action="merge",
            statement="我似乎长期做教育科技方向",
            category="goal",
            origin="inferred",
            confidence=0.8,
        ),
        conversation_id="c2",
    )
    assert r2["ok"]
    fact = store.get_fact(fid)
    assert fact["status"] in ("candidate", "confirmed")
    assert fact["status"] != "stale"


def test_stale_noop_same_statement_revives(tmp_path):
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    stmt = "我偏好简洁回答"
    r1 = resolver.apply(
        SlotAction(
            slot_key="preference.response_style",
            action="new",
            statement=stmt,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    fid = r1["fact"]["id"]
    store.set_status(fid, "stale")
    r2 = resolver.apply(
        SlotAction(
            slot_key="preference.response_style",
            action="noop",
            statement=stmt,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c2",
    )
    assert r2["ok"]
    assert store.get_fact(fid)["status"] == "confirmed"
    assert len(store.list_confirmed()) == 1


def test_stale_noop_inferred_does_not_demote_direct(tmp_path):
    """stale+direct 事实被 inferred noop 触碰时，不得降成 candidate。"""
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    stmt = "我偏好简洁回答"
    r1 = resolver.apply(
        SlotAction(
            slot_key="preference.response_style",
            action="new",
            statement=stmt,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    fid = r1["fact"]["id"]
    store.set_status(fid, "stale")
    r2 = resolver.apply(
        SlotAction(
            slot_key="preference.response_style",
            action="noop",
            statement=stmt,
            category="preference",
            origin="inferred",
            confidence=0.8,
        ),
        conversation_id="c2",
    )
    assert r2["ok"]
    fact = store.get_fact(fid)
    assert fact["origin"] == "direct"
    assert fact["status"] == "confirmed"
    assert store.list_confirmed()


def test_noop_upgrades_candidate_origin_to_direct(tmp_path):
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    stmt = "我似乎偏好简洁回答"
    resolver.apply(
        SlotAction(
            slot_key="preference.response_style",
            action="new",
            statement=stmt,
            category="preference",
            origin="inferred",
            confidence=0.8,
        ),
        conversation_id="c1",
    )
    assert store.list_candidates()
    resolver.apply(
        SlotAction(
            slot_key="preference.response_style",
            action="noop",
            statement=stmt,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    confirmed = store.list_confirmed()
    assert len(confirmed) == 1
    assert confirmed[0]["origin"] == "direct"
    assert store.list_candidates() == []


def test_topic_replace_tombstones_old_so_reextract_cannot_fork(tmp_path):
    """topic_* merge/replace 迁槽后须 tombstone 旧值，防止旧表述再抽成平行 confirmed。"""
    from app.engine.memory.normalize import value_hash

    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    old_stmt = "我周末常去爬山锻炼"
    new_stmt = "我周末常去游泳锻炼"
    r1 = resolver.apply(
        SlotAction(
            slot_key="",
            action="new",
            statement=old_stmt,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    assert r1["ok"]
    old_slot = r1["fact"]["slot_key"]
    assert ".topic_" in old_slot
    r2 = resolver.apply(
        SlotAction(
            slot_key=old_slot,
            action="replace",
            statement=new_stmt,
            category="preference",
            origin="direct",
            confidence=0.95,
        ),
        conversation_id="c2",
    )
    assert r2["ok"]
    assert r2["fact"]["slot_key"] != old_slot
    assert store.has_tombstone(
        slot_key=old_slot, normalized_value_hash=value_hash(old_stmt)
    )
    r3 = resolver.apply(
        SlotAction(
            slot_key="",
            action="new",
            statement=old_stmt,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c3",
    )
    assert not r3.get("ok")
    assert r3.get("error") == "tombstoned"
    assert len(store.list_confirmed()) == 1
    assert "游泳" in store.list_confirmed()[0]["statement"]

    # 类目漂移不得绕过指纹 tombstone
    r4 = resolver.apply(
        SlotAction(
            slot_key="",
            action="new",
            statement=old_stmt,
            category="goal",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c4",
    )
    assert not r4.get("ok")
    assert r4.get("error") == "tombstoned"
    assert len(store.list_confirmed()) == 1


def test_seed_replace_tombstones_old_value(tmp_path):
    """种子槽会话 replace 后，旧表述不得再抽回覆盖。"""
    from app.engine.memory.normalize import value_hash

    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    old = "默认使用英文"
    new = "默认使用中文"
    resolver.apply(
        SlotAction(
            slot_key="preference.response_language",
            action="new",
            statement=old,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    resolver.apply(
        SlotAction(
            slot_key="preference.response_language",
            action="replace",
            statement=new,
            category="preference",
            origin="direct",
            confidence=0.95,
        ),
        conversation_id="c2",
    )
    assert store.has_value_tombstone(value_hash(old))
    r3 = resolver.apply(
        SlotAction(
            slot_key="preference.response_language",
            action="new",
            statement=old,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c3",
    )
    assert not r3.get("ok")
    assert r3.get("error") == "tombstoned"
    assert store.list_confirmed()[0]["statement"] == new


def test_noop_slot_promote_updates_category(tmp_path):
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    stmt = "我正在推进家庭教育长期方案"
    r1 = resolver.apply(
        SlotAction(
            slot_key="",
            action="new",
            statement=stmt,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    assert ".topic_" in r1["fact"]["slot_key"]
    r2 = resolver.apply(
        SlotAction(
            slot_key="goal.active_project",
            action="noop",
            statement=stmt,
            category="goal",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c2",
    )
    assert r2["ok"]
    assert r2["fact"]["id"] == r1["fact"]["id"]
    assert r2["fact"]["slot_key"] == "goal.active_project"
    assert r2["fact"]["category"] == "goal"


def test_same_value_on_seed_does_not_fork_topic(tmp_path):
    """种子/抽象槽已有同值时，不得再开 topic_* 平行条。"""
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    stmt = "我正在推进家庭教育长期方案"
    r1 = resolver.apply(
        SlotAction(
            slot_key="goal.active_project",
            action="new",
            statement=stmt,
            category="goal",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    assert r1["ok"]
    assert r1["fact"]["slot_key"] == "goal.active_project"
    r2 = resolver.apply(
        SlotAction(
            slot_key="",
            action="new",
            statement=stmt,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c2",
    )
    assert r2["ok"]
    assert r2["fact"]["id"] == r1["fact"]["id"]
    assert len(store.list_confirmed()) == 1
    assert ".topic_" not in store.list_confirmed()[0]["slot_key"]


def test_forget_non_topic_blocks_relearn_via_topic(tmp_path):
    """遗忘抽象槽后，同值不得落到 topic_* 回潮。"""
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    stmt = "我偏好厚涂插画冷色调清晰线条风格"
    r1 = resolver.apply(
        SlotAction(
            slot_key="preference.art_style",
            action="new",
            statement=stmt,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    store.mark_forgotten(r1["fact"]["id"])
    r2 = resolver.apply(
        SlotAction(
            slot_key="",
            action="new",
            statement=stmt,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c2",
    )
    assert not r2.get("ok")
    assert r2.get("error") == "tombstoned"
    assert store.list_confirmed() == []


def test_topic_category_migrate_does_not_fork_same_value(tmp_path):
    """同句仅 category 变更迁槽后，原类目再抽不得平行开第二条。"""
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    stmt = "我长期在研究家庭教育路径规划"
    r1 = resolver.apply(
        SlotAction(
            slot_key="",
            action="new",
            statement=stmt,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    assert r1["ok"]
    fid = r1["fact"]["id"]
    assert r1["fact"]["slot_key"].startswith("preference.topic_")
    r2 = resolver.apply(
        SlotAction(
            slot_key=r1["fact"]["slot_key"],
            action="merge",
            statement=stmt,
            category="goal",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c2",
    )
    assert r2["ok"]
    assert r2["fact"]["id"] == fid
    assert r2["fact"]["slot_key"].startswith("goal.topic_")
    r3 = resolver.apply(
        SlotAction(
            slot_key="",
            action="new",
            statement=stmt,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c3",
    )
    assert r3["ok"]
    assert r3["fact"]["id"] == fid
    assert len(store.list_confirmed()) == 1
    # 类目可随入参回写并迁回 preference.topic_*；关键是仍同一条、不平行开槽
    from app.engine.memory.normalize import value_hash

    tip = f".topic_{value_hash(stmt)[:12]}"
    assert store.list_confirmed()[0]["slot_key"].endswith(tip)


def test_remember_clear_tombstone_clears_topic_fingerprint(tmp_path):
    """显式重新记住须清掉迁槽后挂在旧 topic_* 上的 tombstone。"""
    from app.engine.memory.normalize import value_hash
    from app.engine.memory.service import MemoryService
    from app.storage.repo import KnowledgeRepo
    from tests.helpers import make_writer

    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    svc = MemoryService(store, repo, knowledge_writer=make_writer(repo, tmp_path))
    resolver = SlotResolver(store)
    old_stmt = "我周末常去攀岩锻炼"
    new_stmt = "我周末常去骑行锻炼"
    r1 = resolver.apply(
        SlotAction(
            slot_key="",
            action="new",
            statement=old_stmt,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    old_slot = r1["fact"]["slot_key"]
    resolver.apply(
        SlotAction(
            slot_key=old_slot,
            action="replace",
            statement=new_stmt,
            category="preference",
            origin="direct",
            confidence=0.95,
        ),
        conversation_id="c2",
    )
    assert store.has_topic_fingerprint_tombstone(
        normalized_value_hash=value_hash(old_stmt)
    )
    out = svc.remember(old_stmt, clear_tombstone=True)
    assert out.get("ok")
    assert any(old_stmt in (f.get("statement") or "") for f in store.list_confirmed())


def test_stale_paraphrase_aligns_to_same_slot(tmp_path):
    """衰减后近义句应对齐到原槽并复活，不得平行开 topic_ 槽。"""
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    resolver = SlotResolver(store)
    stmt1 = "我喜欢厚涂插画并且偏好冷色调与清晰线条"
    stmt2 = "我偏好厚涂插画冷色调清晰线条风格"
    r1 = resolver.apply(
        SlotAction(
            slot_key="preference.art_style",
            action="new",
            statement=stmt1,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    fid = r1["fact"]["id"]
    store.set_status(fid, "stale")
    r2 = resolver.apply(
        SlotAction(
            slot_key="",
            action="merge",
            statement=stmt2,
            category="preference",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c2",
    )
    assert r2["ok"]
    confirmed = store.list_confirmed()
    assert len(confirmed) == 1
    assert confirmed[0]["id"] == fid
    assert confirmed[0]["slot_key"] == "preference.art_style"
    assert store.get_fact(fid)["status"] == "confirmed"
