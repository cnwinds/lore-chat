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
