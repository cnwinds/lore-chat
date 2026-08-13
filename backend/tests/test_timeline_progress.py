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
