"""tool query 截断。"""

from app.engine.chat.tool_query import TOOL_QUERY_MAX_CHARS, clip_tool_query
from app.engine.chat.timeline import TimelineAccumulator


def test_clip_tool_query_truncates():
    long = "x" * (TOOL_QUERY_MAX_CHARS + 50)
    out = clip_tool_query(long)
    assert out == "x" * TOOL_QUERY_MAX_CHARS + "…"
    assert clip_tool_query("  hi  ") == "hi"
    assert clip_tool_query("   ") == ""


def test_timeline_stores_clipped_command():
    long = "y" * (TOOL_QUERY_MAX_CHARS + 10)
    acc = TimelineAccumulator()
    acc.accumulate(
        "tool_start",
        {
            "id": "1",
            "tool": "sandbox_run",
            "label": "run",
            "ts": "t0",
            "input": {"command": long},
        },
    )
    assert acc.timeline[0]["query"] == "y" * TOOL_QUERY_MAX_CHARS + "…"
