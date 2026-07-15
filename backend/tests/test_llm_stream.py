"""LLM 流式：reasoning_content → think_delta 与诊断日志。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.config import Settings
from app.models.llm import ChatStreamChunk, OpenAILLMClient


def _chunk(*, content=None, reasoning=None, tool_calls=None, finish_reason=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    if reasoning is not None:
        delta.reasoning_content = reasoning
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def test_stream_yields_think_delta_from_reasoning_content():
    llm = OpenAILLMClient(Settings())
    stream = [
        _chunk(reasoning="分析"),
        _chunk(reasoning="问题"),
        _chunk(content="结论", finish_reason="stop"),
    ]

    with patch.object(llm._big.chat.completions, "create", return_value=iter(stream)):
        chunks = list(
            llm.stream_chat_with_tools(
                [{"role": "user", "content": "hi"}],
                [],
                big=True,
            )
        )

    think = [c.think_delta for c in chunks if c.think_delta]
    text = [c.text_delta for c in chunks if c.text_delta]
    final = chunks[-1].result

    assert think == ["分析", "问题"]
    assert text == ["结论"]
    assert final is not None
    assert final.content == "结论"
    assert final.tool_calls == []


def test_stream_logs_truncated_tool_calls(caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="lorechat.llm")
    llm = OpenAILLMClient(Settings())
    partial_tc = SimpleNamespace(
        index=0,
        id="call_x",
        function=SimpleNamespace(name=None, arguments='{"q":'),
    )
    stream = [
        _chunk(tool_calls=[partial_tc]),
    ]

    with patch.object(llm._big.chat.completions, "create", return_value=iter(stream)):
        chunks = list(
            llm.stream_chat_with_tools(
                [{"role": "user", "content": "hi"}],
                [{"type": "function", "function": {"name": "search_kb", "parameters": {}}}],
                big=True,
            )
        )

    assert chunks[-1].result is not None
    assert chunks[-1].result.tool_calls == []
    assert any("truncated tool_calls" in r.message for r in caplog.records)
