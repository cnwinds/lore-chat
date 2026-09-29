"""OpenSandboxRuntime：过期 sandbox 会话自动重建（失败时，而非热路径探活）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.engine.sandbox import state as sandbox_state
from app.engine.sandbox.opensandbox_runtime import OpenSandboxRuntime
from app.engine.sandbox.protocol import SandboxNotFound
from tests.opensandbox_fakes import FakeJobCommands, sdk_api_error


def _runtime(tmp_path) -> OpenSandboxRuntime:
    rt = OpenSandboxRuntime(kb_path=tmp_path, domain="localhost")
    rt._applying_mirrors = True
    return rt


@pytest.mark.asyncio
async def test_ensure_ready_reuses_cached_session_without_probe(tmp_path):
    """热路径不跑探活命令；已缓存句柄直接返回。"""
    rt = _runtime(tmp_path)
    commands = FakeJobCommands()
    rt._sandbox = SimpleNamespace(id="cached-id", sandbox_id="cached-id", commands=commands)
    rt._sandbox_id = "cached-id"

    sid = await rt.ensure_ready()

    assert sid == "cached-id"
    assert commands.started == []


@pytest.mark.asyncio
async def test_run_recovers_after_connect_error(tmp_path):
    rt = _runtime(tmp_path)
    good_commands = FakeJobCommands({"echo ok": ["ok\n"]})
    good = SimpleNamespace(id="live-id", sandbox_id="live-id", commands=good_commands)
    rt._sandbox = SimpleNamespace(
        commands=SimpleNamespace(
            run=AsyncMock(side_effect=httpx.ConnectError("stale"))
        )
    )
    rt._sandbox_id = "stale-id"

    create_mock = AsyncMock(return_value=good)
    with patch("opensandbox.Sandbox.create", create_mock):
        result = await rt.run("echo ok")

    assert result.exit_code == 0
    assert result.output == "ok\n"
    assert create_mock.await_count == 1


@pytest.mark.asyncio
async def test_write_files_recovers_after_sandbox_not_found(tmp_path):
    rt = _runtime(tmp_path)
    write_ok = AsyncMock(return_value=None)
    good = SimpleNamespace(
        id="live-id",
        sandbox_id="live-id",
        files=SimpleNamespace(write_files=write_ok),
        commands=FakeJobCommands(),
    )
    rt._sandbox = SimpleNamespace(
        files=SimpleNamespace(
            write_files=AsyncMock(
                side_effect=Exception(
                    "Sandbox x not found. | [DOCKER::SANDBOX_NOT_FOUND]"
                )
            )
        ),
        commands=FakeJobCommands(),
    )
    rt._sandbox_id = "stale-id"
    sandbox_state.save_sandbox_id(tmp_path, "stale-id")

    with patch("opensandbox.Sandbox.create", AsyncMock(return_value=good)):
        await rt.write_files([("/workspace/a.txt", b"hi")])

    write_ok.assert_awaited_once()
    assert rt._sandbox_id == "live-id"
    assert sandbox_state.load_sandbox_id(tmp_path) == "live-id"


@pytest.mark.asyncio
async def test_is_recoverable_detects_sandbox_not_found():
    exc = Exception(
        "Get endpoint failed: Sandbox x not found. | [DOCKER::SANDBOX_NOT_FOUND]"
    )
    assert OpenSandboxRuntime._is_recoverable_sandbox_error(exc)
    assert OpenSandboxRuntime._is_recoverable_sandbox_error(
        sdk_api_error("DOCKER::SANDBOX_NOT_FOUND", "Sandbox abc not found.", status=404)
    )
    assert not OpenSandboxRuntime._is_recoverable_sandbox_error(
        ValueError("bad command")
    )


@pytest.mark.parametrize(
    ("code", "message", "status"),
    [
        ("FILE_NOT_FOUND", "file not found. open /workspace/x: no such file or directory", 404),
        ("RUNTIME_ERROR", "error accessing file: open /workspace/a/x: not a directory", 500),
    ],
)
def test_file_level_api_errors_are_not_recoverable(code, message, status):
    """文件级 404 / 非目录不是「沙箱没了」，不得触发重建。"""
    exc = sdk_api_error(code, message, status=status)
    assert not OpenSandboxRuntime._is_recoverable_sandbox_error(exc)


@pytest.mark.asyncio
async def test_read_missing_file_raises_not_found_without_recreate(tmp_path):
    rt = _runtime(tmp_path)
    missing = sdk_api_error(
        "FILE_NOT_FOUND",
        "file not found. open /workspace/nope: no such file or directory",
        status=404,
    )
    rt._sandbox = SimpleNamespace(
        files=SimpleNamespace(read_bytes=AsyncMock(side_effect=missing)),
        commands=FakeJobCommands(),
    )
    rt._sandbox_id = "live-id"
    sandbox_state.save_sandbox_id(tmp_path, "live-id")

    create_mock = AsyncMock()
    with patch("opensandbox.Sandbox.create", create_mock):
        with pytest.raises(SandboxNotFound) as ei:
            await rt.read_file("/workspace/nope")

    assert ei.value.path == "/workspace/nope"
    create_mock.assert_not_awaited()
    assert rt._sandbox_id == "live-id"
    assert sandbox_state.load_sandbox_id(tmp_path) == "live-id"
