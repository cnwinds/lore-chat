from app.engine.memory.normalize import (
    align_existing_slot,
    is_abstract_slot_key,
    match_seed_slot,
    normalize_slot_key,
    value_hash,
)


def test_visualization_paraphrases_share_seed_slot():
    a = "我偏好用数据可视化（如榜单、词云等）替代插图。"
    b = "我偏好只用数据可视化元素（如榜单、词云、分布图）来替代插图，而不是使用AI生成的图片。"
    slot_a = match_seed_slot(a) or normalize_slot_key("preference", a)
    slot_b = match_seed_slot(b) or normalize_slot_key("preference", b)
    assert slot_a == slot_b
    assert slot_a == "preference.illustration_style"


def test_normalize_accepts_explicit_predicate():
    assert normalize_slot_key("preference", "illustration_style") == "preference.illustration_style"
    assert normalize_slot_key("preference", "preference.illustration_style") == (
        "preference.illustration_style"
    )


def test_value_hash_still_distinguishes_wording():
    a = "我偏好用数据可视化（如榜单、词云等）替代插图。"
    b = "我偏好只用数据可视化元素（如榜单、词云、分布图）来替代插图，而不是使用AI生成的图片。"
    assert value_hash(a) != value_hash(b)


def test_open_slot_has_no_statement_stem():
    slot = normalize_slot_key("preference", "我喜欢在周五下午整理笔记并归档。")
    assert slot.startswith("preference.topic_")
    assert "周五" not in slot
    assert "整理" not in slot
    assert not slot.startswith("preference.open_")
    assert is_abstract_slot_key(slot)


def test_paraphrases_align_to_existing_abstract_slot():
    a = "我喜欢在周五下午整理笔记并归档。"
    b = "我偏好周五下午把笔记整理好再归档。"
    first = normalize_slot_key("preference", a)
    second = normalize_slot_key(
        "preference",
        b,
        existing=[{"slot_key": first, "statement": a, "category": "preference"}],
    )
    assert second == first
    assert align_existing_slot(
        b,
        category="preference",
        existing=[{"slot_key": first, "statement": a, "category": "preference"}],
    ) == first


def test_legacy_open_stem_not_treated_as_abstract():
    assert not is_abstract_slot_key(
        "preference.open_我偏好用数据可视化_如榜单_abc123def0"
    )


def test_unrelated_short_prefs_do_not_align():
    a = "我喜欢喝咖啡"
    b = "我喜欢喝茶"
    first = normalize_slot_key("preference", a)
    assert (
        align_existing_slot(
            b,
            category="preference",
            existing=[{"slot_key": first, "statement": a, "category": "preference"}],
        )
        is None
    )
