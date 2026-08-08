"""AGENTS.md：常识提及 ≠ 画像事实（根因同类验收，非孤例补丁）。"""

from app.engine.memory.llm_extractor import LLMMemoryExtractor
from app.engine.memory.llm_extractor import _SYSTEM_PROMPT as MSG_PROMPT
from app.engine.memory.prompt_common import (
    NON_DURABLE_IGNORE,
    OWNER_MEMORY_GATE,
    SCOPE_FIDELITY_GATE,
    passes_owner_surface_gate,
)
from app.engine.memory.session_extractor import (
    LLMSessionExtractor,
    RuleBasedSessionExtractor,
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
    assert OWNER_MEMORY_GATE in MSG_PROMPT
    assert NON_DURABLE_IGNORE in SESSION_PROMPT
    assert NON_DURABLE_IGNORE in MSG_PROMPT
    assert SCOPE_FIDELITY_GATE in SESSION_PROMPT
    assert SCOPE_FIDELITY_GATE in MSG_PROMPT


def test_world_knowledge_scale_not_extracted_by_rules():
    """与主人无关的制度说明不得落入启发式抽取。"""
    ext = RuleBasedSessionExtractor()
    actions = ext.extract(
        ["是上海卷660分制下的。 政史地。"],
        confirmed_summary=[],
    )
    assert actions == []


def test_seed_alias_in_world_knowledge_not_extracted_by_rules():
    """含种子别名的常识句不得因别名命中而落槽。"""
    ext = RuleBasedSessionExtractor()
    actions = ext.extract(
        ["matplotlib 常用于数据可视化，榜单和词云都很常见。"],
        confirmed_summary=[],
    )
    assert actions == []


def test_world_knowledge_paraphrase_fails_surface_gate():
    """换一种常识措辞、无主人归属 → 表面门禁仍挡住（根因同类）。"""
    samples = [
        "是上海卷660分制下的。",
        "高考满分一般是750分。",
        "Python 列表是可变序列。",
        "人民币对美元今日汇率波动。",
        "matplotlib 常用于数据可视化。",
        "数据可视化可以用榜单、词云展示。",
    ]
    for s in samples:
        assert not passes_owner_surface_gate(s), s


def test_owner_side_facts_pass_surface_gate():
    assert passes_owner_surface_gate("我孩子高考考了500分")
    assert passes_owner_surface_gate("我偏好用数据可视化替代插图")
    assert passes_owner_surface_gate("默认使用中文")


def test_bare_kinship_word_does_not_pass_gate():
    """裸亲属词不是主人归属；常识句夹带「孩子」不得放行。"""
    assert not passes_owner_surface_gate("孩子高考满分一般是750分")
    assert not passes_owner_surface_gate("父母应关注孩子睡眠")


def test_constraint_alias_without_deixis_does_not_pass_gate():
    """无主人指称时，约束别名短禁令不得当画像（根因：种子≠关于主人）。"""
    assert not passes_owner_surface_gate("不要迟到")
    assert not passes_owner_surface_gate("禁止吸烟")
    # 有指称的主人约束仍可过
    assert passes_owner_surface_gate("我不要你用 AI 生成插图")


def test_seed_slot_key_alone_does_not_bypass_gate():
    """抽象种子 slot 名不能证明语句关于主人。"""
    assert not passes_owner_surface_gate(
        "matplotlib 常用于数据可视化。",
        slot_key="preference.illustration_style",
    )


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


def test_llm_message_extractor_drops_world_knowledge_emit():
    ext = LLMMemoryExtractor(
        _FakeLLM(
            '{"candidates":[{"statement":"上海卷实行660分制。",'
            '"evidence":"是上海卷660分制下的。","category":"preference",'
            '"origin":"direct","confidence":0.9}]}'
        )
    )
    result = ext.extract("是上海卷660分制下的。")
    assert result.candidates == []


def test_owner_family_fact_still_extractable_by_seed_alias():
    """对照：主人侧偏好仍可经种子对齐抽出（同类根因下的正例侧）。"""
    ext = RuleBasedSessionExtractor()
    actions = ext.extract(
        ["我偏好用数据可视化（榜单、词云）替代插图。"],
        confirmed_summary=[],
    )
    assert len(actions) == 1
    assert actions[0].slot_key == "preference.illustration_style"


def test_llm_session_cold_start_paraphrases_share_slot():
    """同批冷启动近义（无种子）应对齐到同一抽象槽。"""
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
    assert actions[0].slot_key == actions[1].slot_key
    assert "周五" not in actions[0].slot_key
