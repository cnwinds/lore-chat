"""OpenSandboxRuntime.run：只走后台 job 通道，输出逐字节还原。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.engine.sandbox import progress
from app.engine.sandbox.opensandbox_runtime import OpenSandboxRuntime
from tests.opensandbox_fakes import FakeJobCommands


def _runtime(tmp_path, commands) -> OpenSandboxRuntime:
    rt = OpenSandboxRuntime(kb_path=tmp_path, domain="localhost")
    rt._sandbox = SimpleNamespace(id="sb", sandbox_id="sb", commands=commands)
    rt._sandbox_id = "sb"
    rt._applying_mirrors = True
    return rt


@pytest.mark.asyncio
async def test_run_concatenates_pages_verbatim(tmp_path):
    # 同步回调通道会把这段吐成 ['a', '\n', 'bc']；job 通道须原样还原
    pages = ["a\n\nb", "c\n", "tail-no-nl"]
    commands = FakeJobCommands({"cmd": pages})
    rt = _runtime(tmp_path, commands)

    result = await rt.run("cmd", cwd="/w")

    assert result.output == "a\n\nbc\ntail-no-nl"
    assert result.exit_code == 0
    assert result.timed_out is False
    assert commands.started[0]["cwd"] == "/w"
    assert rt._active_executions == set()


@pytest.mark.asyncio
async def test_run_reports_exit_code_and_merged_stderr(tmp_path):
    commands = FakeJobCommands(
        {"cmd": ["out1\nls: cannot access 'x': No such file or directory\n"]},
        exit_codes={"cmd": 2},
    )
    rt = _runtime(tmp_path, commands)

    result = await rt.run("cmd")

    assert result.exit_code == 2
    assert "No such file" in result.output


@pytest.mark.asyncio
async def test_run_timeout_interrupts_and_flags(tmp_path):
    commands = FakeJobCommands(running_forever={"sleep"})
    rt = _runtime(tmp_path, commands)

    result = await rt.run("sleep", timeout_sec=0.05)

    assert result.timed_out is True
    assert result.exit_code == 124
    assert commands.interrupted == [result.execution_id]


@pytest.mark.asyncio
async def test_poll_failure_after_start_does_not_rerun_command(tmp_path):
    import httpx

    class FlakyPoll(FakeJobCommands):
        async def get_command_status(self, execution_id):
            raise httpx.ConnectError("connection reset")

    commands = FlakyPoll({"rm -rf /workspace/x": ["done\n"]})
    rt = _runtime(tmp_path, commands)
    rebuilt: list = []
    rt._invalidate_sandbox = lambda **kw: rebuilt.append(kw)  # type: ignore[method-assign]

    with pytest.raises(httpx.ConnectError):
        await rt.run("rm -rf /workspace/x")

    assert [s["command"] for s in commands.started] == ["rm -rf /workspace/x"]
    assert rebuilt == []
    assert commands.interrupted == ["e1"]
    assert rt._active_executions == set()


@pytest.mark.asyncio
async def test_run_timeout_keeps_output_flushed_after_interrupt(tmp_path):
    class TailOnInterrupt(FakeJobCommands):
        async def interrupt(self, execution_id):
            await super().interrupt(execution_id)
            self._jobs[execution_id]["pages"] = ["last words\n"]

    commands = TailOnInterrupt({"job": ["first\n"]}, running_forever={"job"})
    rt = _runtime(tmp_path, commands)

    result = await rt.run("job", timeout_sec=0.05)

    assert result.timed_out is True
    assert result.output == "first\nlast words\n"


@pytest.mark.asyncio
async def test_internal_run_emits_no_progress(tmp_path, monkeypatch):
    emitted: list = []
    monkeypatch.setattr(progress, "emit_progress", lambda *a, **k: emitted.append(a))
    rt = _runtime(tmp_path, FakeJobCommands({"cmd": ["x\n"]}))

    await rt.run("cmd")

    assert emitted == []
