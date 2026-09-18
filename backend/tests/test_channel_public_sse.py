"""脚本通道精简 SSE 投影。"""

import asyncio

from app.engine.agent.events import sse_event
from app.engine.channel_plugins.public_sse import (
    iter_public_chat_sse,
    project_agent_event,
    public_done_event,
    public_start_event,
)
from app.engine.chat.sse import parse_agent_sse_event


def test_project_drops_thinking_and_tools_by_default():
    think = sse_event("think_delta", {"delta": "先想一步"})
    tool = sse_event(
        "tool_start",
        {"id": "t1", "tool": "read_doc", "label": "读文档", "input": {"path": "a.md"}},
    )
    text = sse_event("text_delta", {"delta": "你好"})
    assert project_agent_event(think) is None
    assert project_agent_event(tool) is None
    projected = project_agent_event(text)
    parsed = parse_agent_sse_event(projected)
    assert parsed[0] == "text_delta"
    assert parsed[1]["delta"] == "你好"


def test_project_includes_thinking_and_clipped_tools_when_enabled():
    think = project_agent_event(
        sse_event("think_delta", {"delta": "先想一步"}),
        show_thinking=True,
    )
    assert parse_agent_sse_event(think)[1]["delta"] == "先想一步"

    start = project_agent_event(
        sse_event(
            "tool_start",
            {
                "id": "t1",
                "tool": "read_doc",
                "label": "读文档",
                "input": {"path": "笔记.md"},
            },
        ),
        show_tool_output=True,
    )
    data = parse_agent_sse_event(start)[1]
    assert data["tool"] == "read_doc"
    assert data["query"] == "笔记.md"
    assert "input" not in data

    result = project_agent_event(
        sse_event(
            "tool_result",
            {
                "id": "t1",
                "tool": "read_doc",
                "summary": "找到了",
                "content": "x" * 5000,
            },
        ),
        show_tool_output=True,
    )
    body = parse_agent_sse_event(result)[1]
    assert body["summary"] == "找到了"
    assert body["content"].endswith("…")
    assert len(body["content"]) <= 4000


def test_project_skips_internal_timeline_state():
    raw = sse_event("timeline_state", {"timeline": [], "assistant_text": "hi"})
    assert project_agent_event(raw, show_thinking=True, show_tool_output=True) is None
    visible = sse_event("assistant_visible_set", {"text": "改写后的正文"})
    assert project_agent_event(visible, show_thinking=True, show_tool_output=True) is None
    selected = sse_event("model_selected", {"model": "x"})
    assert project_agent_event(selected) is None


def test_public_start_and_done_shape():
    start = parse_agent_sse_event(public_start_event("c1", "t1"))
    assert start[0] == "start"
    assert start[1]["conversation_id"] == "c1"
    assert start[1]["turn_id"] == "t1"

    done = parse_agent_sse_event(
        public_done_event(
            {
                "conversation_id": "c1",
                "turn_id": "t1",
                "status": "completed",
                "message": {"role": "assistant", "content": "完"},
                "assistant": {
                    "text": "完",
                    "timeline": [{"type": "think", "content": "内部"}],
                    "sources": [{"type": "kb", "path": "a.md"}],
                    "total_duration_ms": 12,
                },
            }
        )
    )
    assert done[0] == "done"
    assert done[1]["message"]["content"] == "完"
    assert "assistant" not in done[1]
    assert done[1]["sources"][0]["path"] == "a.md"
    assert done[1]["total_duration_ms"] == 12

    asked = parse_agent_sse_event(
        public_done_event(
            {
                "conversation_id": "c1",
                "turn_id": "t1",
                "status": "completed",
                "message": {"role": "assistant", "content": ""},
                "assistant": {
                    "timeline": [
                        {
                            "type": "tool",
                            "tool": "ask_user",
                            "awaiting_user": True,
                            "question": "用哪种格式？",
                            "options": ["简报", "详报"],
                        }
                    ]
                },
            }
        )
    )
    assert "用哪种格式？" in asked[1]["needs_input"]
    assert "简报" in asked[1]["needs_input"]


def test_iter_public_chat_sse_start_text_done_hides_trace():
    async def source():
        yield sse_event("think_delta", {"delta": "先想一步"})
        yield sse_event(
            "tool_start",
            {"id": "t1", "tool": "search_kb", "label": "检索"},
        )
        yield sse_event("text_delta", {"delta": "你好"})
        yield sse_event("done", {"sources": [], "total_duration_ms": 3})

    async def collect():
        events = []
        async for ev in iter_public_chat_sse(
            source(),
            conversation_id="c1",
            turn_id="t1",
            done_payload=lambda: {
                "conversation_id": "c1",
                "turn_id": "t1",
                "status": "completed",
                "message": {"role": "assistant", "content": "你好"},
            },
        ):
            events.append(parse_agent_sse_event(ev))
        return events

    events = asyncio.run(collect())
    types = [item[0] for item in events]
    assert types[0] == "start"
    assert types[-1] == "done"
    assert "text_delta" in types
    assert "think_delta" not in types
    assert "tool_start" not in types
    assert events[-1][1]["message"]["content"] == "你好"
    assert events[-1][1]["total_duration_ms"] == 3
