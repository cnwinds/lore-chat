"""沙箱产出跨轮可见：执行结束探测 /workspace 新写文件 → 工具块 → 下一轮【本轮产出】。"""

from __future__ import annotations

import json
import os
import subprocess
import time

import pytest

from app.engine.agent.tool_events import emit_tool_result_sse
from app.engine.chat.sse import parse_agent_sse_event
from app.engine.chat.timeline import TimelineAccumulator
from app.engine.conversation.transcript import ConversationTranscript
from app.engine.sandbox import probes
from app.engine.sandbox.execution_engine import SandboxExecutionEngine
from app.engine.sandbox.fake_runtime import FakeSandboxRuntime
from app.engine.sandbox.protocol import CommandResult
from app.models.llm import ToolCall


def _run_script(root, **kw) -> dict:
    config = probes.workspace_outputs_config(root=str(root), **kw)
    proc = subprocess.run(
        ["bash", "-c", probes.workspace_outputs_command(config)],
        capture_output=True,
        text=True,
        check=False,
    )
    return probes.decode_workspace_outputs(
        CommandResult(output=proc.stdout + proc.stderr, exit_code=proc.returncode)
    )


def _write(root, rel: str, data: str = "x", *, age: float = 0.0) -> str:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data)
    if age:
        t = time.time() - age
        os.utime(path, (t, t))
    return str(path)


def test_script_lists_recent_files_and_prunes_other_scopes(tmp_path):
    mine = _write(tmp_path, "conversations/c1/report.json", "abc")
    shared = _write(tmp_path, "games.csv", "1234")
    _write(tmp_path, "old.txt", age=3600)
    _write(tmp_path, "conversations/c2/theirs.json")
    _write(tmp_path, "schedules/s9/nightly.log")
    _write(tmp_path, ".cache/pip/wheel")
    _write(tmp_path, "proj/node_modules/pkg/index.js")
    _write(tmp_path, "proj/__pycache__/m.pyc")
    _write(tmp_path, "proj/.hidden")

    out = _run_script(tmp_path, age_sec=60, conversation_id="c1")

    assert sorted(f["path"] for f in out["files"]) == sorted([mine, shared])
    assert {f["path"]: f["size"] for f in out["files"]}[shared] == 4
    assert out["truncated"] is False


def test_script_orders_newest_first_and_marks_truncation(tmp_path):
    for i in range(5):
        _write(tmp_path, f"f{i}.txt", age=50 - i * 10)

    out = _run_script(tmp_path, age_sec=60, limit=3)

    assert [os.path.basename(f["path"]) for f in out["files"]] == ["f4.txt", "f3.txt", "f2.txt"]
    assert out["truncated"] is True


def test_script_scans_own_scope_before_hitting_scan_cap(tmp_path):
    for i in range(10):
        _write(tmp_path, f"build/target/obj{i}.o")
    mine = _write(tmp_path, "conversations/c1/result.json")

    out = _run_script(tmp_path, age_sec=60, conversation_id="c1", scan=3)

    assert mine in [f["path"] for f in out["files"]]
    assert out["truncated"] is True


def test_script_schedule_scope_keeps_own_dir_only(tmp_path):
    mine = _write(tmp_path, "schedules/s1/out.md")
    _write(tmp_path, "schedules/s2/out.md")
    _write(tmp_path, "conversations/c1/chat.md")

    out = _run_script(tmp_path, age_sec=60, schedule_id="s1")

    assert [f["path"] for f in out["files"]] == [mine]


def test_script_missing_root_is_empty(tmp_path):
    out = _run_script(tmp_path / "nope", age_sec=60)
    assert out == {"files": [], "truncated": False}


def _engine() -> SandboxExecutionEngine:
    return SandboxExecutionEngine(poll_interval_sec=0.01, emit=lambda *a, **k: None)


@pytest.mark.asyncio
async def test_engine_reports_files_written_by_command():
    rt = FakeSandboxRuntime()
    await rt.write_file("/workspace/conversations/c2/theirs.json", b"{}")

    out = await _engine().execute(
        rt,
        command="echo hi > /workspace/conversations/c1/games.json",
        cwd="/workspace/conversations/c1",
        conversation_id="c1",
    )

    assert out["exit_code"] == 0
    assert out["workspace_outputs"] == {
        "files": [{"path": "/workspace/conversations/c1/games.json", "size": 3}],
        "truncated": False,
    }


@pytest.mark.asyncio
async def test_engine_omits_outputs_when_nothing_written():
    out = await _engine().execute(FakeSandboxRuntime(), command="echo hi")
    assert out["exit_code"] == 0
    assert "workspace_outputs" not in out


@pytest.mark.asyncio
async def test_engine_probe_failure_keeps_command_result():
    rt = FakeSandboxRuntime()
    real_run = rt.run

    async def run(command, **kw):
        if probes.WORKSPACE_OUTPUTS_SCRIPT in command:
            raise RuntimeError("boom")
        return await real_run(command, **kw)

    rt.run = run  # type: ignore[method-assign]
    out = await _engine().execute(rt, command="echo hi > /workspace/a.txt")

    assert out["exit_code"] == 0
    assert out["summary"] == "命令完成 exit=0"
    assert "workspace_outputs" not in out


@pytest.mark.asyncio
async def test_engine_stop_reports_outputs():
    rt = FakeSandboxRuntime()
    engine = _engine()
    first = await engine.execute(rt, command="__stream_echo__", wait_sec=0.1)
    await rt.write_file("/workspace/partial.csv", b"a,b\n")

    stopped = await engine.stop(rt, first["execution_id"])

    assert stopped["stopped"] is True
    assert [f["path"] for f in stopped["workspace_outputs"]["files"]] == [
        "/workspace/partial.csv"
    ]


def _turn_with_sandbox_result(out: dict) -> dict:
    """一轮 sandbox_run：经 SSE 事件与时间线累加器落成持久化的助手消息。"""
    acc = TimelineAccumulator()
    acc.accumulate(
        "tool_start",
        {"id": "t1", "tool": "sandbox_run", "label": "沙箱", "ts": 0,
         "input": {"command": "python fetch.py"}},
    )
    tc = ToolCall(id="t1", name="sandbox_run", arguments={"command": "python fetch.py"})
    event, data = parse_agent_sse_event(emit_tool_result_sse(tc, out, 10))
    acc.accumulate(event, data)
    acc.accumulate("text_delta", {"delta": "数据已拉取。", "ts": 1})
    return {"role": "assistant", "timeline": json.loads(json.dumps(acc.timeline))}


def test_next_turn_history_lists_sandbox_files_from_previous_turn():
    out = {
        "summary": "命令完成 exit=0",
        "sources": [],
        "exit_code": 0,
        "stdout": "ok\n",
        "workspace_outputs": {
            "files": [
                {"path": "/workspace/conversations/c1/games.json", "size": 2048},
                {"path": "/workspace/conversations/c1/run.log", "size": 12},
            ],
            "truncated": True,
        },
    }
    conv = {
        "messages": [
            {"role": "user", "text": "拉一下最近一个月的游戏类型"},
            _turn_with_sandbox_result(out),
            {"role": "user", "text": "用刚才的文件做个统计"},
        ]
    }

    content = ConversationTranscript.llm_history(conv)[1]["content"]

    assert content.startswith("数据已拉取。")
    assert "【本轮产出】\n沙箱文件（未入库）：" in content
    assert "- /workspace/conversations/c1/games.json（2.0 KB）" in content
    assert "- /workspace/conversations/c1/run.log（12 B）" in content
    assert "仅列最近修改的部分文件" in content


def test_footer_combines_kb_outputs_and_sandbox_files():
    msg = {
        "role": "assistant",
        "text": "好了",
        "attachments": ["媒体/生成/2026-09/chart.png"],
        "timeline": [
            {
                "type": "parallel",
                "children": [
                    {
                        "type": "tool",
                        "tool": "sandbox_run",
                        "status": "done",
                        "workspace_outputs": {
                            "files": [{"path": "/workspace/a.csv", "size": 5}],
                            "truncated": False,
                        },
                    }
                ],
            },
            {
                "type": "tool",
                "tool": "sandbox_run",
                "status": "done",
                "workspace_outputs": {
                    "files": [{"path": "/workspace/a.csv", "size": 9}],
                    "truncated": False,
                },
            },
        ],
    }

    content = ConversationTranscript.llm_assistant_content(msg)

    assert content == (
        "好了\n\n【本轮产出】\n- 媒体/生成/2026-09/chart.png\n"
        "沙箱文件（未入库）：\n- /workspace/a.csv（9 B）"
    )


def test_turn_sandbox_outputs_caps_merged_list():
    block = lambda start: {  # noqa: E731
        "type": "tool",
        "tool": "sandbox_run",
        "workspace_outputs": {
            "files": [{"path": f"/workspace/f{i}", "size": 1} for i in range(start, start + 20)],
            "truncated": False,
        },
    }
    msg = {"role": "assistant", "timeline": [block(0), block(20), block(40)]}

    merged = ConversationTranscript.turn_sandbox_outputs(msg)

    assert len(merged["files"]) == 30
    assert merged["truncated"] is True


def test_sandbox_files_ignored_on_unrelated_tools():
    msg = {
        "role": "assistant",
        "text": "查到了",
        "timeline": [
            {
                "type": "tool",
                "tool": "sandbox_list_dir",
                "status": "done",
                "workspace_outputs": {"files": [{"path": "/workspace/x", "size": 1}]},
            }
        ],
    }
    assert ConversationTranscript.llm_assistant_content(msg) == "查到了"
