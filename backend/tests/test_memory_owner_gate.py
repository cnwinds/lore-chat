"""AGENTS.md：常识提及 ≠ 画像事实（根因同类验收，非孤例补丁）。"""

from app.engine.memory.prompt_common import (
    NON_DURABLE_IGNORE,
    OWNER_MEMORY_GATE,
    SCOPE_FIDELITY_GATE,
    passes_owner_surface_gate,
)
from app.engine.memory.session_extractor import (
    LLMSessionExtractor,
    _SYSTEM_PROMPT as SESSION_PROMPT,
)


class _FakeLLM:
    def __init__(self, payload: str):
        self.payload = payload

    def chat(self, _messages, **_kwargs):
        return self.payload


def test_owner_gate_shared_by_extractors():
    assert "删掉该句后主人画像是否变少" in OWNER_MEMORY_GATE
    assert "制度、常识" in OWNER_MEMORY_GATE
    assert OWNER_MEMORY_GATE in SESSION_PROMPT
    assert NON_DURABLE_IGNORE in SESSION_PROMPT
    assert SCOPE_FIDELITY_GATE in SESSION_PROMPT


def test_world_knowledge_paraphrase_fails_surface_gate():
    """换一种常识措辞、无主人归属 → 表面门禁仍挡住（根因同类）。"""
    samples = [
        "是上海卷660分制下的。",
        "高考满分一般是750分。",
        "Python 列表是可变序列。",
        "人民币对美元今日汇率波动。",
        "matplotlib 常用于数据可视化。",
        "数据可视化可以用榜单、词云展示。",
        "默认使用中文",  # 无第一人称：归属由 LLM 写成「我…」后再过门禁
        "不要迟到",
        "禁止吸烟",
    ]
    for s in samples:
        assert not passes_owner_surface_gate(s), s


def test_owner_side_facts_pass_surface_gate():
    assert passes_owner_surface_gate("我孩子高考考了500分")
    assert passes_owner_surface_gate("我偏好用数据可视化替代插图")
    assert passes_owner_surface_gate("我默认使用中文")
    assert passes_owner_surface_gate("我不要你用 AI 生成插图")


def test_bare_kinship_word_does_not_pass_gate():
    """裸亲属词不是主人归属；常识句夹带「孩子」不得放行。"""
    assert not passes_owner_surface_gate("孩子高考满分一般是750分")
    assert not passes_owner_surface_gate("父母应关注孩子睡眠")


def test_seed_alias_text_without_deixis_does_not_pass_gate():
    """含种子别名的常识句、无主人指称 → 不得放行。"""
    assert not passes_owner_surface_gate("matplotlib 常用于数据可视化。")
    assert not passes_owner_surface_gate("数据可视化可以用榜单、词云展示。")


def test_llm_session_drops_world_knowledge_even_if_model_emits():
    """LLM 路径：模型若误吐常识伪画像，后置门禁丢弃。"""
    ext = LLMSessionExtractor(
        _FakeLLM(
            '{"items":[{"slot_key":"preference.illustration_style","action":"new",'
            '"statement":"matplotlib常用于数据可视化。","category":"preference",'
            '"origin":"direct","confidence":0.9}]}'
        )
    )
    assert ext.extract(
        ["matplotlib 常用于数据可视化。"], confirmed_summary=[]
    ) == []


def test_llm_session_keeps_owner_preference():
    """对照：带主人指称的偏好经 LLM 路径可抽出。"""
    stmt = "我偏好用数据可视化（榜单、词云）替代插图。"
    ext = LLMSessionExtractor(
        _FakeLLM(
            '{"items":[{"slot_key":"preference.illustration_style","action":"new",'
            f'"statement":"{stmt}","category":"preference",'
            '"origin":"direct","confidence":0.9}]}'
        )
    )
    actions = ext.extract([stmt], confirmed_summary=[])
    assert len(actions) == 1
    assert actions[0].slot_key == "preference.illustration_style"


def test_llm_session_cold_start_paraphrases_share_slot(tmp_path):
    """同批冷启动近义：抽取器透传 hint；SlotResolver 写入时对齐到同一抽象槽。"""
    from app.engine.memory.resolver import SlotResolver
    from app.engine.memory.store import MemoryStore

    a = "我喜欢在周五下午整理笔记并归档到知识库。"
    b = "我偏好周五下午把笔记整理好再归档进知识库。"
    ext = LLMSessionExtractor(
        _FakeLLM(
            '{"items":['
            f'{{"slot_key":"preference.topic_aaaa","action":"new","statement":"{a}",'
            '"category":"preference","origin":"direct","confidence":0.9},'
            f'{{"slot_key":"preference.topic_bbbb","action":"new","statement":"{b}",'
            '"category":"preference","origin":"direct","confidence":0.9}'
            "]}"
        )
    )
    actions = ext.extract([a, b], confirmed_summary=[])
    assert len(actions) == 2
    # 抽取器不再做批内对齐，hint 可不同
    assert actions[0].slot_key != actions[1].slot_key

    store = MemoryStore(tmp_path / "memory.db", owner_key="test")
    resolver = SlotResolver(store)
    out_a = resolver.apply(actions[0], conversation_id="c1")
    out_b = resolver.apply(actions[1], conversation_id="c1")
    assert out_a["ok"] and out_b["ok"]
    # merge 后可能 sync topic_* 指纹；最终应并成一条存活事实
    confirmed = store.list_confirmed()
    assert len(confirmed) == 1
    assert out_a["fact"]["id"] == out_b["fact"]["id"] or out_b["fact"][
        "id"
    ] == confirmed[0]["id"]
    assert "周五" not in confirmed[0]["slot_key"]
