"""沙箱结果：summary 只报状态、输出只在 stdout；界面与审批续跑拼展示文本。"""

from __future__ import annotations

import json

from app.engine.agent.tool_events import emit_tool_result_sse
from app.engine.sandbox.result_text import (
    DISPLAY_MAX_CHARS,
    LOG_TAIL_CHARS,
    MODEL_STDOUT_HEAD_CHARS,
    MODEL_STDOUT_MAX_CHARS,
    clip_stdout,
    display_summary,
)
from app.models.llm import ToolCall


def _sse_payload(ev: str) -> dict:
    data = next(line for line in ev.splitlines() if line.startswith("data: "))
    return json.loads(data[len("data: ") :])


def test_display_summary_joins_status_and_logs():
    out = {"summary": "命令完成 exit=0", "stdout": "hello\n"}
    assert display_summary(out) == "命令完成 exit=0\nhello"


def test_display_summary_without_logs_is_status_only():
    assert display_summary({"summary": "命令完成 exit=0", "stdout": "  \n"}) == (
        "命令完成 exit=0"
    )


def test_display_summary_finished_keeps_head_running_keeps_tail():
    logs = "HEAD" + "x" * 10000 + "TAIL"
    done = display_summary({"summary": "命令完成 exit=0", "stdout": logs})
    assert len(done) == DISPLAY_MAX_CHARS
    assert "HEAD" in done and "TAIL" not in done

    for flag in ("running", "stopped"):
        text = display_summary({"summary": "s", "stdout": logs, flag: True})
        assert text.endswith("TAIL")
        assert "HEAD" not in text
        assert len(text) <= len("s\n") + LOG_TAIL_CHARS


def test_clip_stdout_passes_short_logs_through():
    logs = "x" * MODEL_STDOUT_MAX_CHARS
    assert clip_stdout(logs) == {"stdout": logs}


def test_clip_stdout_keeps_head_and_tail_of_long_logs():
    logs = "HEAD" + "m" * 100_000 + "TRACEBACK"
    out = clip_stdout(logs)
    assert out["stdout_truncated"] is True
    assert out["stdout_total_chars"] == len(logs)
    text = out["stdout"]
    assert text.startswith("HEAD")
    assert text.endswith("TRACEBACK")
    omitted = len(logs) - MODEL_STDOUT_MAX_CHARS
    assert f"中间省略 {omitted} 字" in text
    assert "sandbox_read_file" in text
    assert len(text) < MODEL_STDOUT_MAX_CHARS + 200
    assert text[:MODEL_STDOUT_HEAD_CHARS] == logs[:MODEL_STDOUT_HEAD_CHARS]


def test_emit_tool_result_uses_display_text_for_sandbox_logs():
    tc = ToolCall(id="t1", name="sandbox_run", arguments={"command": "echo hi"})
    out = {"summary": "命令完成 exit=0", "stdout": "hi\n", "sources": []}
    payload = _sse_payload(emit_tool_result_sse(tc, out, 5))
    assert payload["summary"] == "命令完成 exit=0\nhi"


def test_emit_tool_result_other_tools_keep_summary():
    tc = ToolCall(id="t2", name="read_doc", arguments={"path": "a.md"})
    out = {"summary": "读取 a.md", "stdout": "not a sandbox log", "sources": []}
    payload = _sse_payload(emit_tool_result_sse(tc, out, 5))
    assert payload["summary"] == "读取 a.md"
