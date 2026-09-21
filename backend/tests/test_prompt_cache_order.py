"""提示词缓存顺序：逐轮变化的内容（当前时间）必须位于整条提示词最末。"""

from app.engine.agent.message_builder import build_agent_messages
from app.engine.agent.prompts import build_system_prompt


def test_system_prompt_does_not_carry_time():
    system = build_system_prompt("default")
    # 规则文字可引用【当前时间】，但时间块本体（「当前时刻」）必须在用户消息里
    assert "当前时刻" not in system


def test_time_block_lands_in_last_user_message():
    messages = build_agent_messages(
        "帮我看看这段",
        mode="default",
        web_enabled=False,
        system_layer_text="",
        user_memory="",
        history=[{"role": "user", "content": "之前的问题"}],
        active_doc_path=None,
        active_doc_paths=None,
        primary_doc_path=None,
    )
    assert messages[0]["role"] == "system"
    assert "当前时刻" not in messages[0]["content"]
    last = messages[-1]
    assert last["role"] == "user"
    assert last["content"].startswith("【当前时间】")
    assert "帮我看看这段" in last["content"]


def test_time_block_changes_but_history_prefix_stable():
    """两次调用只有时间块与用户文本不同；其前的消息序列完全一致。"""
    common = dict(
        mode="default",
        web_enabled=False,
        system_layer_text="",
        user_memory="",
        history=[{"role": "user", "content": "之前的问题"}],
        active_doc_path=None,
        active_doc_paths=None,
        primary_doc_path=None,
    )
    first = build_agent_messages("问题一", **common)
    second = build_agent_messages("问题二", **common)
    # 除首条（含时间）与末条（用户文本）外，中间消息一致
    assert first[1:-1] == second[1:-1]
    # 首条 system 在两次调用间完全一致（时间已移出）
    assert first[0] == second[0]
