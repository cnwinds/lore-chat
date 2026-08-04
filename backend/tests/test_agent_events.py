import json
from app.engine.agent.events import (
    now_ts, sse_event, tool_start, tool_result, text_delta, done,
)


def test_sse_event_format():
    ev = tool_start("t1", "search_kb", "检索本地知识库", {"query": "x"})
    assert ev.startswith("event: tool_start\n")
    data = json.loads(ev.split("data: ", 1)[1].strip())
    assert data["id"] == "t1"
    assert "ts" in data


def test_tool_result_with_content():
    ev = tool_result("t1", "fetch_url", "Example", content="# Hello")
    data = json.loads(ev.split("data: ", 1)[1].strip())
    assert data["content"] == "# Hello"


def test_tool_result_with_ask_user_fields():
    ev = tool_result(
        "t1",
        "ask_user",
        "等待用户选择",
        question_id="q1",
        question="请选择",
        options=[{"id": "a", "label": "选项 A"}],
        multi_select=False,
    )
    data = json.loads(ev.split("data: ", 1)[1].strip())
    assert data["question_id"] == "q1"
    assert data["options"][0]["label"] == "选项 A"


def test_now_ts_uses_china_offset():
    ts = now_ts()
    assert "+08:00" in ts
