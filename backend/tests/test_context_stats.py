"""上下文容量分项：记忆单列，并按真实装配估算 token。"""

from types import SimpleNamespace

from app.engine.agent.prompts import SYSTEM_PROMPT, wrap_user_memory
from app.engine.usage.context_stats import (
    build_context_stats,
    estimate_tokens,
)


class _Usage:
    def conversation_usage_totals(self, _cid: str) -> dict:
        return {
            "last_prompt_tokens": None,
            "last_model": None,
            "cache_tokens": 0,
            "prompt_tokens": 0,
            "cost_total": None,
            "turns_with_usage": 0,
        }


class _Models:
    def context_limit(self, _model, _provider):
        return 128000


class _Layer:
    def __init__(self, memory: str = "", rules: str = "心法与戒律正文"):
        self._memory = memory
        self._rules = rules

    def compose_rules(self) -> str:
        return self._rules

    def compose(self) -> str:
        return self._rules

    def memory_context(self) -> str:
        return self._memory


def _stats(conversation, *, memory="", usage=None, **kwargs):
    return build_context_stats(
        conversation=conversation,
        roles=None,
        system_layer=_Layer(memory),
        usage_store=usage or _Usage(),
        models_dev=_Models(),
        chat_models=[],
        **kwargs,
    )


def _seg(body, key):
    return next(s for s in body["segments"] if s["key"] == key)


def test_estimate_tokens_cjk_heavier_than_latin():
    assert estimate_tokens("你") == 1
    assert estimate_tokens("abcd") == 1  # 4 * 0.3 = 1


def test_segments_always_include_memory():
    body = _stats({"id": "c1", "messages": []})
    keys = [s["key"] for s in body["segments"]]
    assert keys == [
        "system",
        "memory",
        "skill",
        "history",
        "tools",
        "attachments",
    ]
    assert _seg(body, "memory")["tokens"] == 0
    assert _seg(body, "memory")["preview"] == ""


def test_memory_is_separate_and_matches_wrap():
    fact = "- 我工作日晚上通常只有约 1 小时可支配"
    body = _stats({"id": "c1", "messages": []}, memory=fact)
    mem = _seg(body, "memory")
    assert mem["preview"] == fact
    assert mem["tokens"] == estimate_tokens(wrap_user_memory(fact))
    assert mem["tokens"] > 0
    system = _seg(body, "system")
    assert system["tokens"] > estimate_tokens("心法与戒律正文")
    assert system["tokens"] >= estimate_tokens(SYSTEM_PROMPT) * 0.8


def test_history_uses_llm_window_not_all_messages():
    pad = "字" * 800
    messages = []
    for i in range(40):
        messages.append({"role": "user", "text": f"用户第{i}轮 {pad}"})
        messages.append({"role": "assistant", "text": f"助手第{i}轮 {pad}"})
    body = _stats({"id": "c1", "messages": messages})
    history = _seg(body, "history")
    all_text = "".join(m["text"] for m in messages)
    # llm_history：最多 20 个 user turn，且总长 ≤ 32000
    assert history["tokens"] < estimate_tokens(all_text)
    assert history["tokens"] > 0
    assert history["tokens"] <= estimate_tokens("字" * 32000)


def test_system_includes_builtin_prompt():
    body = _stats({"id": "c1", "messages": []})
    system = _seg(body, "system")
    assert system["tokens"] >= estimate_tokens(SYSTEM_PROMPT) * 0.8


def test_used_tokens_remainder_goes_to_tools():
    class Usage(_Usage):
        def conversation_usage_totals(self, _cid: str) -> dict:
            base = super().conversation_usage_totals(_cid)
            base["last_prompt_tokens"] = 50_000
            return base

    body = _stats({"id": "c1", "messages": []}, usage=Usage())
    total = sum(s["tokens"] for s in body["segments"])
    assert total == 50_000
    assert _seg(body, "tools")["tokens"] > 10_000


def test_attachments_only_count_last_user_message():
    body = _stats(
        {
            "id": "c1",
            "messages": [
                {
                    "role": "user",
                    "text": "看这张",
                    "attachments": ["媒体/旧图.png"],
                },
                {"role": "assistant", "text": "好"},
                {
                    "role": "user",
                    "text": "再看",
                    "attachments": ["媒体/新图.png"],
                },
            ],
        }
    )
    att = _seg(body, "attachments")
    # 只计最后一条用户消息的一张识图，不是两张
    assert att["tokens"] == 765


def test_last_turn_tool_content_not_recounted():
    """上一轮工具正文不再回传下一轮，不计入注入估算；按需经工具取回。"""
    body = _stats(
        {
            "id": "c1",
            "messages": [
                {"role": "user", "text": "查一下"},
                {
                    "role": "assistant",
                    "text": "找到了",
                    "timeline": [
                        {
                            "type": "tool",
                            "tool": "search_kb",
                            "summary": "短摘要",
                            "content": "检索正文" * 80,
                        }
                    ],
                },
            ],
        }
    )
    tools = _seg(body, "tools")
    # 未配置工具目录时工具段为空：上一轮检索正文不再被当作下一轮注入
    assert tools["tokens"] == 0


def test_select_tools_includes_read_last_tool_results():
    from app.engine.agent.tool_catalog import select_tools

    names = {
        d["function"]["name"]
        for d in select_tools("default", web_enabled=False)
    }
    assert "read_last_tool_results" in names


def test_skill_catalog_counts_injected_text():
    body = _stats(
        {"id": "c1", "messages": []},
        skill_catalog=[
            {
                "name": "demo",
                "description": "演示技能触发条件写在这里",
                "entry": "技能/demo/SKILL.md",
                "root": "技能/demo",
            }
        ],
    )
    skill = _seg(body, "skill")
    assert skill["tokens"] > 0
    assert "演示技能" in str(skill) or skill["tokens"] >= estimate_tokens(
        "演示技能触发条件写在这里"
    )
