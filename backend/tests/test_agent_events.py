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


def test_now_ts_has_timezone():
    ts = now_ts()
    assert "T" in ts
