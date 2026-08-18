from app.engine.agent.message_builder import build_agent_messages
from app.engine.agent.prompts import DEMO_ENVIRONMENT_CONTRACT, MODE_DEFAULT


def _system_text(messages):
    return "\n".join(m["content"] for m in messages if m.get("role") == "system")


def _build(**kwargs):
    defaults = dict(
        mode=MODE_DEFAULT,
        web_enabled=False,
        system_layer_text="",
        user_memory="",
        history=None,
        active_doc_path=None,
        active_doc_paths=None,
        primary_doc_path=None,
    )
    defaults.update(kwargs)
    return build_agent_messages("你好", **defaults)


def test_demo_contract_present_when_demo():
    messages = _build(demo_mode=True)
    assert DEMO_ENVIRONMENT_CONTRACT in _system_text(messages)


def test_demo_contract_absent_by_default():
    messages = _build()
    assert DEMO_ENVIRONMENT_CONTRACT not in _system_text(messages)


def test_contract_states_environment_not_phrasing_rules():
    """写环境契约，不写话术黑名单——后者只能挡住原句。"""
    assert "演示" in DEMO_ENVIRONMENT_CONTRACT
    assert "预览" in DEMO_ENVIRONMENT_CONTRACT
    assert "不会被保存" in DEMO_ENVIRONMENT_CONTRACT
