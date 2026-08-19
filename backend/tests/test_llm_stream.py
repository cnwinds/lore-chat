"""LLM 流式：reasoning_content → think_delta 与诊断日志。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.config import Settings
from app.models.llm import (
    OpenAILLMClient,
    _api_messages_have_images,
)


def _chunk(*, content=None, reasoning=None, tool_calls=None, finish_reason=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    if reasoning is not None:
        delta.reasoning_content = reasoning
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _mock_select():
    return SimpleNamespace(
        candidate=SimpleNamespace(
            id="test",
            model="test-model",
            thinking=False,
            effort="",
            effort_options=(),
            thinking_protocol="none",
        ),
        failover=False,
        skipped=[],
    )


def test_api_messages_have_images():
    assert not _api_messages_have_images([{"role": "user", "content": "hi"}])
    assert _api_messages_have_images(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "看图"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}},
                ],
            }
        ]
    )


def test_stream_with_images_uses_non_stream_completion():
    """有图时走同步 completions，再合成 think/text/result（避免流式+图挂死）。"""
    llm = OpenAILLMClient(Settings())
    msg = SimpleNamespace(
        content="图里是猫",
        reasoning_content="先看图",
        tool_calls=None,
    )
    resp = SimpleNamespace(
        choices=[SimpleNamespace(message=msg, finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = resp

    vision_messages = [
        {
            "role": "user",
            "content": "描述图片",
            "attachments": ["shot.png"],
        }
    ]

    with (
        patch.object(llm, "_client_for", return_value=mock_client),
        patch.object(
            llm,
            "_materialize",
            return_value=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "描述图片"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "https://example/x.png"},
                        },
                    ],
                }
            ],
        ),
        patch.object(
            llm,
            "_select",
            return_value=SimpleNamespace(
                candidate=SimpleNamespace(
                    id="vision",
                    model="agnes-2.5-flash",
                    thinking=False,
                    effort="",
                    effort_options=(),
                    thinking_protocol="none",
                ),
                failover=False,
                skipped=[],
            ),
        ),
    ):
        chunks = list(llm.stream_chat_with_tools(vision_messages, [], big=True))

    create_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert create_kwargs.get("stream") is not True
    assert "stream_options" not in create_kwargs

    think = [c.think_delta for c in chunks if c.think_delta]
    text = [c.text_delta for c in chunks if c.text_delta]
    finals = [c for c in chunks if c.result is not None]
    assert think == ["先看图"]
    assert text == ["图里是猫"]
    assert finals[-1].result is not None
    assert finals[-1].result.content == "图里是猫"


def test_stream_yields_think_delta_from_reasoning_content():
    llm = OpenAILLMClient(Settings())
    stream = [
        _chunk(reasoning="分析"),
        _chunk(reasoning="问题"),
        _chunk(content="结论", finish_reason="stop"),
    ]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter(stream)

    with (
        patch.object(llm, "_client_for", return_value=mock_client),
        patch.object(llm, "_select", return_value=_mock_select()),
    ):
        chunks = list(
            llm.stream_chat_with_tools(
                [{"role": "user", "content": "hi"}],
                [],
                big=True,
            )
        )

    think = [c.think_delta for c in chunks if c.think_delta]
    text = [c.text_delta for c in chunks if c.text_delta]
    finals = [c for c in chunks if c.result is not None]
    final = finals[-1].result

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
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter(stream)

    with (
        patch.object(llm, "_client_for", return_value=mock_client),
        patch.object(llm, "_select", return_value=_mock_select()),
    ):
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
