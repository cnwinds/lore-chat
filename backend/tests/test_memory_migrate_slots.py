from app.engine.memory.migrate_slots import migrate_abstract_slots
from app.engine.memory.normalize import value_hash
from app.engine.memory.store import MemoryStore


def test_migrate_merges_visualization_stem_slots(tmp_path):
    store = MemoryStore(tmp_path / "m.db", owner_key="ws1")
    a = "我偏好用数据可视化（如榜单、词云等）替代插图。"
    b = "我偏好只用数据可视化元素（如榜单、词云、分布图）来替代插图，而不是使用AI生成的图片。"
    store.upsert_fact(
        slot_key="preference.我偏好用数据可视化_如榜单_词云等_替代插图_",
        category="preference",
        statement=a,
        normalized_value_hash=value_hash(a),
        origin="direct",
    )
    store.upsert_fact(
        slot_key="preference.我偏好只用数据可视化元素_如榜单_词云_分布图_来替代插图_而不是使用ai生成的图片_",
        category="preference",
        statement=b,
        normalized_value_hash=value_hash(b),
        origin="direct",
    )
    assert len(store.list_confirmed()) == 2
    result = migrate_abstract_slots(store, dry_run=False)
    assert result["superseded"] >= 1
    confirmed = store.list_confirmed()
    assert len(confirmed) == 1
    assert confirmed[0]["slot_key"] == "preference.illustration_style"


def test_migrate_reports_new_predicate_candidates(tmp_path):
    store = MemoryStore(tmp_path / "m3.db", owner_key="ws1")
    a = "我喜欢在周五下午整理笔记并归档到知识库。"
    store.upsert_fact(
        slot_key="preference.open_旧茎_",
        category="preference",
        statement=a,
        normalized_value_hash=value_hash(a),
        origin="direct",
    )
    result = migrate_abstract_slots(store, dry_run=True)
    assert "new_predicates" in result
    assert isinstance(result["new_predicates"], list)


def test_migrate_llm_rejects_non_owner_canonical(tmp_path):
    store = MemoryStore(tmp_path / "m5.db", owner_key="ws1")
    a = "我喜欢周五整理笔记。"
    fa = store.upsert_fact(
        slot_key="preference.open_a",
        category="preference",
        statement=a,
        normalized_value_hash=value_hash(a),
        origin="direct",
    )

    class BadLLM:
        def chat(self, _messages, **_kw):
            import json

            return json.dumps(
                {
                    "groups": [
                        {
                            "slot_key": "preference.exam_scale",
                            "category": "preference",
                            "statement": "上海卷实行660分制。",
                            "fact_ids": [fa["id"]],
                        }
                    ],
                    "new_predicates": [],
                },
                ensure_ascii=False,
            )

    migrate_abstract_slots(store, dry_run=False, llm=BadLLM())
    # 伪自述被门禁丢弃 → 回落启发式，仍保留主人原句
    confirmed = store.list_confirmed()
    assert len(confirmed) == 1
    assert "笔记" in confirmed[0]["statement"]
    assert confirmed[0]["slot_key"] != "preference.exam_scale"


def test_migrate_llm_can_override_grouping(tmp_path):
    store = MemoryStore(tmp_path / "m4.db", owner_key="ws1")
    a = "我喜欢周五整理笔记。"
    b = "我偏好周五把笔记归档。"
    fa = store.upsert_fact(
        slot_key="preference.open_a",
        category="preference",
        statement=a,
        normalized_value_hash=value_hash(a),
        origin="direct",
    )
    fb = store.upsert_fact(
        slot_key="preference.open_b",
        category="preference",
        statement=b,
        normalized_value_hash=value_hash(b),
        origin="direct",
    )

    class FakeLLM:
        def chat(self, _messages, **_kw):
            import json

            return json.dumps(
                {
                    "groups": [
                        {
                            "slot_key": "preference.friday_notes",
                            "category": "preference",
                            "statement": "我偏好周五整理并归档笔记。",
                            "fact_ids": [fa["id"], fb["id"]],
                        }
                    ],
                    "new_predicates": [
                        {
                            "slot_key": "preference.friday_notes",
                            "reason": "周五笔记习惯",
                        }
                    ],
                },
                ensure_ascii=False,
            )

    result = migrate_abstract_slots(store, dry_run=False, llm=FakeLLM())
    assert result["used_llm"] is True
    assert result["superseded"] >= 1
    confirmed = store.list_confirmed()
    assert len(confirmed) == 1
    assert confirmed[0]["slot_key"] == "preference.friday_notes"


def test_migrate_merges_open_hash_paraphrases_without_seed(tmp_path):
    store = MemoryStore(tmp_path / "m2.db", owner_key="ws1")
    a = "我喜欢在周五下午整理笔记并归档到知识库。"
    b = "我偏好周五下午把笔记整理好再归档进知识库。"
    store.upsert_fact(
        slot_key="preference.open_我喜欢在周五下午整理笔记_aabbccddee",
        category="preference",
        statement=a,
        normalized_value_hash=value_hash(a),
        origin="direct",
    )
    store.upsert_fact(
        slot_key="preference.open_我偏好周五下午把笔记整理好_ffeeddccbb",
        category="preference",
        statement=b,
        normalized_value_hash=value_hash(b),
        origin="direct",
    )
    result = migrate_abstract_slots(store, dry_run=False)
    assert result["superseded"] >= 1
    confirmed = store.list_confirmed()
    assert len(confirmed) == 1
    assert confirmed[0]["slot_key"].startswith("preference.topic_")
    assert "周五" not in confirmed[0]["slot_key"]
