"""timeline 累积 tool_progress。"""

from app.engine.chat.timeline import TimelineAccumulator


def test_tool_progress_concatenates_chunks():
    acc = TimelineAccumulator()
    acc.accumulate(
        "tool_start",
        {"id": "1", "tool": "sandbox_run", "label": "run", "ts": "t0"},
    )
    acc.accumulate(
        "tool_progress",
        {"id": "1", "tool": "sandbox_run", "message": "$ ls\n", "ts": "t1"},
    )
    acc.accumulate(
        "tool_progress",
        {"id": "1", "tool": "sandbox_run", "message": "a", "ts": "t2"},
    )
    acc.accumulate(
        "tool_progress",
        {"id": "1", "tool": "sandbox_run", "message": "b\n", "ts": "t3"},
    )
    block = acc.timeline[0]
    assert block["progress_log"] == ["$ ls\na\nb\n"]
    assert isinstance(block.get("started_at_ms"), int)


def test_tool_progress_skips_noise():
    acc = TimelineAccumulator()
    acc.accumulate(
        "tool_start",
        {"id": "1", "tool": "sandbox_run", "label": "run", "ts": "t0"},
    )
    acc.accumulate(
        "tool_progress",
        {"id": "1", "message": "仍在运行… 90s", "ts": "t1"},
    )
    assert acc.timeline[0].get("progress_log") in (None, [])


def test_tool_start_stamps_started_at_ms_and_keeps_it():
    acc = TimelineAccumulator()
    acc.accumulate(
        "tool_start",
        {
            "id": "1",
            "tool": "fetch_url",
            "label": "打开链接",
            "ts": "t0",
            "started_at_ms": 1_700_000_000_000,
        },
    )
    assert acc.timeline[0]["started_at_ms"] == 1_700_000_000_000
    acc.accumulate(
        "tool_progress",
        {"id": "1", "tool": "fetch_url", "message": "still going"},
    )
    assert acc.timeline[0]["started_at_ms"] == 1_700_000_000_000


def test_tool_start_stores_command_as_query():
    acc = TimelineAccumulator()
    acc.accumulate(
        "tool_start",
        {
            "id": "1",
            "tool": "sandbox_run",
            "label": "run",
            "ts": "t0",
            "input": {"command": "echo hi && sleep 1"},
        },
    )
    assert acc.timeline[0]["query"] == "echo hi && sleep 1"


def test_tool_start_stores_generate_image_prompt_as_query():
    acc = TimelineAccumulator()
    acc.accumulate(
        "tool_start",
        {
            "id": "1",
            "tool": "generate_image",
            "label": "生图",
            "ts": "t0",
            "input": {"prompt": "一只橙色的猫，坐在窗台上"},
        },
    )
    assert acc.timeline[0]["query"] == "一只橙色的猫，坐在窗台上"


def test_interrupted_payload_marks_running_tools():
    acc = TimelineAccumulator()
    acc.accumulate(
        "tool_start",
        {"id": "1", "tool": "sandbox_run", "label": "run", "ts": "t0"},
    )
    payload = acc.assistant_payload("interrupted")
    assert payload["status"] == "interrupted"
    assert payload["timeline"][0]["status"] == "interrupted"
    assert "连接中断" in payload["timeline"][0]["summary"]


def test_done_tokens_land_in_assistant_payload():
    acc = TimelineAccumulator()
    acc.accumulate(
        "done",
        {
            "sources": [],
            "total_duration_ms": 1200,
            "prompt_tokens": 12345,
            "completion_tokens": 678,
        },
    )
    payload = acc.assistant_payload("complete")
    assert payload["prompt_tokens"] == 12345
    assert payload["completion_tokens"] == 678
    assert payload["total_duration_ms"] == 1200


def test_error_payload_fills_text_and_status():
    acc = TimelineAccumulator()
    payload = acc.assistant_payload("interrupted", error="网关超时")
    assert payload["status"] == "error"
    assert payload["text"] == "错误：网关超时"
    assert payload["error"] == "网关超时"


def test_generate_image_clears_progress_log_on_result():
    acc = TimelineAccumulator()
    acc.accumulate(
        "tool_start",
        {"id": "1", "tool": "generate_image", "label": "生图", "ts": "t0"},
    )
    acc.accumulate(
        "tool_progress",
        {"id": "1", "message": "百炼生成中（RUNNING）.", "ts": "t1"},
    )
    assert acc.timeline[0].get("progress_log")
    acc.accumulate(
        "tool_result",
        {
            "id": "1",
            "summary": "已生成图片 → generated/x.png（bailian）",
            "attachments": ["generated/x.png"],
            "sources": [],
        },
    )
    assert "progress_log" not in acc.timeline[0]
    assert acc.timeline[0]["attachments"] == ["generated/x.png"]


def test_assistant_visible_set_replaces_trailing_text():
    acc = TimelineAccumulator()
    acc.accumulate("think_delta", {"delta": "thinking", "ts": "t0"})
    acc.accumulate(
        "text_delta",
        {"delta": "前言\n\n【征询】选哪个？ 选项：A；B", "ts": "t1"},
    )
    assert acc.assistant_text.endswith("选项：A；B")
    acc.accumulate("assistant_visible_set", {"text": "前言", "ts": "t2"})
    assert acc.assistant_text == "前言"
    types = [b["type"] for b in acc.timeline]
    assert types == ["think", "text"]
    assert acc.timeline[1]["content"] == "前言"


def test_assistant_visible_set_drops_empty_text():
    acc = TimelineAccumulator()
    acc.accumulate("text_delta", {"delta": "【征询】选哪个？ 选项：A；B", "ts": "t0"})
    acc.accumulate("assistant_visible_set", {"text": "", "ts": "t1"})
    assert acc.assistant_text == ""
    assert acc.timeline == []


def test_think_closed_by_text_has_duration_ms(monkeypatch):
    times = iter([100.0, 101.5])
    monkeypatch.setattr("app.engine.chat.timeline.time.monotonic", lambda: next(times))
    acc = TimelineAccumulator()
    acc.accumulate("think_delta", {"delta": "thinking", "ts": "t0"})
    acc.accumulate("text_delta", {"delta": "answer", "ts": "t1"})
    think = acc.timeline[0]
    assert think["type"] == "think"
    assert think["duration_ms"] == 1500
    assert acc.timeline[1]["type"] == "text"


def test_think_closed_by_tool_has_duration_ms(monkeypatch):
    times = iter([50.0, 51.0])
    monkeypatch.setattr("app.engine.chat.timeline.time.monotonic", lambda: next(times))
    acc = TimelineAccumulator()
    acc.accumulate("think_delta", {"delta": "thinking", "ts": "t0"})
    acc.accumulate(
        "tool_start",
        {"id": "1", "tool": "sandbox_run", "label": "run", "ts": "t1"},
    )
    assert acc.timeline[0]["type"] == "think"
    assert acc.timeline[0]["duration_ms"] == 1000
    assert acc.timeline[1]["type"] == "tool"


def test_think_closed_on_done(monkeypatch):
    times = iter([10.0, 12.0])
    monkeypatch.setattr("app.engine.chat.timeline.time.monotonic", lambda: next(times))
    acc = TimelineAccumulator()
    acc.accumulate("think_delta", {"delta": "thinking", "ts": "t0"})
    acc.accumulate("done", {"sources": [], "total_duration_ms": 12})
    assert acc.timeline[0]["duration_ms"] == 2000


def test_think_after_text_starts_new_block(monkeypatch):
    times = iter([1.0, 2.0, 3.0])
    monkeypatch.setattr("app.engine.chat.timeline.time.monotonic", lambda: next(times))
    acc = TimelineAccumulator()
    acc.accumulate("think_delta", {"delta": "a", "ts": "t0"})
    acc.accumulate("text_delta", {"delta": "b", "ts": "t1"})
    acc.accumulate("think_delta", {"delta": "c", "ts": "t2"})
    assert [b["type"] for b in acc.timeline] == ["think", "text", "think"]
    assert acc.timeline[0]["duration_ms"] == 1000
    assert "duration_ms" not in acc.timeline[2]
