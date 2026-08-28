"""OpenSandboxRuntime：过期 sandbox 会话自动重建。"""

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
async def test_probe_failure_invalidates_cached_session(tmp_path):
    rt = _runtime(tmp_path)
    rt._sandbox = SimpleNamespace(
        commands=SimpleNamespace(run=AsyncMock(side_effect=httpx.ConnectError("down")))
    )
    rt._sandbox_id = "dead-id"
    sandbox_state.save_sandbox_id(tmp_path, "dead-id")

    assert await rt._probe_sandbox() is False

    created = _sandbox_with_run(AsyncMock(return_value=SimpleNamespace(exit_code=0)))
    with patch(
        "opensandbox.Sandbox.create",
        AsyncMock(return_value=created),
    ):
        sid = await rt.ensure_ready()

    assert sid == "live-id"
    assert sandbox_state.load_sandbox_id(tmp_path) == "live-id"


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
async def test_is_recoverable_detects_sandbox_not_found():
    exc = Exception(
        "Get endpoint failed: Sandbox x not found. | [DOCKER::SANDBOX_NOT_FOUND]"
    )
    assert OpenSandboxRuntime._is_recoverable_sandbox_error(exc)
    assert not OpenSandboxRuntime._is_recoverable_sandbox_error(
        ValueError("bad command")
    )
