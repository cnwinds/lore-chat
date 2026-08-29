"""OpenSandboxRuntime：过期 sandbox 会话自动重建（失败时，而非热路径探活）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.engine.sandbox import state as sandbox_state
from app.engine.sandbox.opensandbox_runtime import OpenSandboxRuntime


def _runtime(tmp_path) -> OpenSandboxRuntime:
    rt = OpenSandboxRuntime(kb_path=tmp_path, domain="localhost")
    rt._applying_mirrors = True
    return rt


def _sandbox_with_run(run: AsyncMock) -> SimpleNamespace:
    return SimpleNamespace(
        id="live-id",
        sandbox_id="live-id",
        commands=SimpleNamespace(run=run),
    )


@pytest.mark.asyncio
async def test_ensure_ready_reuses_cached_session_without_probe(tmp_path):
    """热路径不跑 commands.run('true')；已缓存句柄直接返回。"""
    rt = _runtime(tmp_path)
    probe_run = AsyncMock(return_value=SimpleNamespace(exit_code=0))
    rt._sandbox = SimpleNamespace(
        id="cached-id",
        sandbox_id="cached-id",
        commands=SimpleNamespace(run=probe_run),
    )
    rt._sandbox_id = "cached-id"

    sid = await rt.ensure_ready()

    assert sid == "cached-id"
    probe_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_recovers_after_connect_error(tmp_path):
    rt = _runtime(tmp_path)
    good_run = AsyncMock(
        return_value=SimpleNamespace(id="e1", exit_code=0, logs=None)
    )
    good = _sandbox_with_run(good_run)
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
    assert create_mock.await_count == 1
    assert good_run.await_count >= 1


@pytest.mark.asyncio
async def test_write_files_recovers_after_sandbox_not_found(tmp_path):
    rt = _runtime(tmp_path)
    write_ok = AsyncMock(return_value=None)
    good = SimpleNamespace(
        id="live-id",
        sandbox_id="live-id",
        files=SimpleNamespace(write_files=write_ok),
        commands=SimpleNamespace(run=AsyncMock()),
    )
    rt._sandbox = SimpleNamespace(
        files=SimpleNamespace(
            write_files=AsyncMock(
                side_effect=Exception(
                    "Sandbox x not found. | [DOCKER::SANDBOX_NOT_FOUND]"
                )
            )
        ),
        commands=SimpleNamespace(run=AsyncMock()),
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
    assert not OpenSandboxRuntime._is_recoverable_sandbox_error(
        ValueError("bad command")
    )
