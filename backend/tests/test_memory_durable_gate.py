"""耐久性 + 语境保全门槛：根因同类验收（非孤例补丁）。"""

from app.engine.memory.llm_extractor import _SYSTEM_PROMPT as MSG_PROMPT
from app.engine.memory.prompt_common import (
    NON_DURABLE_IGNORE,
    OWNER_MEMORY_GATE,
    SCOPE_FIDELITY_GATE,
    passes_owner_surface_gate,
)
from app.engine.memory.session_extractor import (
    _SYSTEM_PROMPT as SESSION_PROMPT,
    compress_dialogue_timeline,
)


def test_durable_and_scope_gates_shared_by_extractors():
    assert "跨会话仍成立" in NON_DURABLE_IGNORE or "短期活动" in NON_DURABLE_IGNORE
    assert "过度概括" in SCOPE_FIDELITY_GATE
    assert OWNER_MEMORY_GATE in SESSION_PROMPT
    assert NON_DURABLE_IGNORE in SESSION_PROMPT
    assert SCOPE_FIDELITY_GATE in SESSION_PROMPT
    assert NON_DURABLE_IGNORE in MSG_PROMPT
    assert SCOPE_FIDELITY_GATE in MSG_PROMPT


def test_ephemeral_task_paraphrases_documented_as_non_durable():
    """换措辞的阶段性任务仍属同一根因类（原则须覆盖，非专名黑名单）。"""
    samples = [
        "我计划重新编写 skill，去掉里面的 pi.dev",
        "我想这次把登录改成 JWT",
        "帮我把这个 PR 的测试补上",
        "我准备把依赖里的某某库卸掉再重写配置",
    ]
    for s in samples:
        # 归属门禁会放行「我…」；耐久性靠 prompt，不在此做关键词丢弃
        assert passes_owner_surface_gate(s), s
    assert "阶段性" in NON_DURABLE_IGNORE or "一次性" in NON_DURABLE_IGNORE


def test_scoped_time_constraint_must_not_become_bare_universal():
    """学习排期喊时间紧 → 不得鼓励抽成无限定通项（语境保全 + 耐久性）。"""
    assert "过度概括" in SCOPE_FIDELITY_GATE
    assert "时间" in NON_DURABLE_IGNORE or "精力" in NON_DURABLE_IGNORE
    # 正例：稳定节奏仍过归属门禁
    assert passes_owner_surface_gate("我工作日晚上通常只有约 1 小时可支配")


def test_dialogue_timeline_keeps_assistant_summary_for_disambiguation():
    turns = [
        ("user", "如果我想学习 FDE，需要准备什么"),
        ("assistant", "这是 6 周路线图，每周 8-12 小时，包含 RAG 练习项目。"),
        ("user", "我每周的时间不多，你帮我改成 8 周路线图"),
    ]
    out = compress_dialogue_timeline(turns, max_chars=5000)
    assert "assistant:" in out
    assert "6 周" in out or "8-12" in out
    assert "时间不多" in out


def test_dialogue_timeline_does_not_treat_assistant_as_owner_statement_for_rules():
    """规则路径只扫 user；纯助手断言不得单独构成画像输入。"""
    from app.engine.memory.session_extractor import RuleBasedSessionExtractor

    ext = RuleBasedSessionExtractor()
    actions = ext.extract(
        [("assistant", "用户每周可支配时间不多，这是硬约束。")],
        confirmed_summary=[],
    )
    assert actions == []


def test_assistant_secret_like_text_does_not_block_user_extract():
    from app.engine.memory.session_extractor import (
        LLMSessionExtractor,
        RuleBasedSessionExtractor,
    )

    ext = RuleBasedSessionExtractor()
    actions = ext.extract(
        [
            ("user", "我偏好用数据可视化替代插图。"),
            ("assistant", "示例 key=sk-abcdefghijklmnopqrstuvwxyz012345"),
        ],
        confirmed_summary=[],
    )
    assert len(actions) == 1
    assert actions[0].slot_key == "preference.illustration_style"

    class _FakeLLM:
        def chat(self, _messages, **_kwargs):
            return (
                '{"items":[{"slot_key":"preference.illustration_style","action":"new",'
                '"statement":"我偏好用数据可视化替代插图。","category":"preference",'
                '"origin":"direct","confidence":0.9}]}'
            )

    llm_actions = LLMSessionExtractor(_FakeLLM()).extract(
        [
            ("user", "我偏好用数据可视化替代插图。"),
            ("assistant", "示例 key=sk-abcdefghijklmnopqrstuvwxyz012345"),
        ],
        confirmed_summary=[],
    )
    assert len(llm_actions) == 1


def test_llm_extractor_skips_secret_user_turn_not_whole_session():
    """含密钥的用户句应跳过，不得否决同会话其它自述。"""
    from app.engine.memory.session_extractor import LLMSessionExtractor

    seen: list[str] = []

    class _FakeLLM:
        def chat(self, messages, **_kwargs):
            # 第二条消息为 user 压缩正文
            seen.append(messages[1]["content"])
            return (
                '{"items":[{"slot_key":"preference.illustration_style","action":"new",'
                '"statement":"我偏好用数据可视化替代插图。","category":"preference",'
                '"origin":"direct","confidence":0.9}]}'
            )

    actions = LLMSessionExtractor(_FakeLLM()).extract(
        [
            ("user", "key=sk-abcdefghijklmnopqrstuvwxyz0123456789"),
            ("user", "我偏好用数据可视化替代插图。"),
        ],
        confirmed_summary=[],
    )
    assert len(actions) == 1
    assert "sk-" not in seen[0]
    assert "数据可视化" in seen[0]
