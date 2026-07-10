import json
from app.models.llm import FakeLLMClient, ToolCall


def test_fake_llm_chat_with_tools_returns_tool_calls():
    tc = ToolCall(id="c1", name="search_kb", arguments={"query": "docker"})
    llm = FakeLLMClient(tool_responses=[
        {"content": None, "tool_calls": [tc]},
        {"content": "docker 用于容器管理", "tool_calls": []},
    ])
    r1 = llm.chat_with_tools([{"role": "user", "content": "docker?"}], tools=[])
    assert r1.content is None
    assert len(r1.tool_calls) == 1
    assert r1.tool_calls[0].name == "search_kb"

    r2 = llm.chat_with_tools([{"role": "user", "content": "continue"}], tools=[])
    assert r2.content == "docker 用于容器管理"
    assert r2.tool_calls == []
