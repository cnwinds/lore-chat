"""SandboxRuntime 端口契约：同一套用例跑所有实现（ADR 2026-09-29 §5）。

- ``fake``：FakeSandboxRuntime，常驻 CI
- ``opensandbox-local``：OpenSandboxRuntime + 本机 bash 替身（输出按 7 字节切页、切断行）
- ``opensandbox-live``：设 ``LORECHAT_SANDBOX_IT=1`` 时连真实 OpenSandbox
  （读 ``OPENSANDBOX_DOMAIN`` / ``OPENSANDBOX_API_KEY`` 等；
  ``LORECHAT_SANDBOX_IT_ROLE`` / ``LORECHAT_SANDBOX_IT_VOLUME`` 指定角色槽位）
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

from app.engine.sandbox.fake_runtime import FakeSandboxRuntime
from app.engine.sandbox.opensandbox_runtime import OpenSandboxRuntime
from app.engine.sandbox.protocol import SandboxNotADirectory, SandboxNotFound
from tests.opensandbox_fakes import local_shell_sandbox

_LIVE = os.environ.get("LORECHAT_SANDBOX_IT") == "1"
_KINDS = ["fake", "opensandbox-local"] + (["opensandbox-live"] if _LIVE else [])
_ODD_NAMES = ["a b.txt", "中文.md", "line\nbreak.txt", "-dash"]


class _Env:
    def __init__(self, runtime, root: str, *, real_shell: bool) -> None:
        self.runtime = runtime
        self.root = root
        self.real_shell = real_shell


@pytest_asyncio.fixture(params=_KINDS)
async def env(request, tmp_path):
    kind = request.param
    if kind == "fake":
        yield _Env(FakeSandboxRuntime(), "/workspace/contract", real_shell=False)
        return
    if kind == "opensandbox-local":
        rt = OpenSandboxRuntime(kb_path=tmp_path, domain="localhost")
        rt._sandbox = local_shell_sandbox()
        rt._sandbox_id = "local-sb"
        rt._applying_mirrors = True
        root = tmp_path / "ws"
        root.mkdir()
        yield _Env(rt, str(root), real_shell=True)
        return

    from app.config import Settings
    from app.engine.sandbox import state as sandbox_state
    from app.engine.sandbox.factory import build_opensandbox_runtime

    rt = build_opensandbox_runtime(
        Settings(),
        role_id=os.environ.get("LORECHAT_SANDBOX_IT_ROLE", "default"),
        workspace_volume=os.environ.get("LORECHAT_SANDBOX_IT_VOLUME") or None,
    )
    # 状态写进临时目录，不碰线上 .kb；给了 sandbox id 就复用现有容器
    rt.kb_path = tmp_path
    existing = os.environ.get("LORECHAT_SANDBOX_IT_ID")
    if existing:
        sandbox_state.upsert_slot(
            tmp_path,
            rt.role_id,
            sandbox_id=existing,
            volume_name=rt.workspace_volume,
            mirror_region=rt.mirror_region,
            default_volume=rt._slot_default_volume,
        )
    await rt.ensure_ready()
    root = f"/workspace/.lorechat-contract-{uuid.uuid4().hex[:8]}"
    await rt.run(f"mkdir -p {root}", cwd="/")
    try:
        yield _Env(rt, root, real_shell=True)
    finally:
        await rt.run(f"rm -rf -- {root}", cwd="/")


async def _seed(env: _Env, names: list[str]) -> None:
    await env.runtime.write_files([(f"{env.root}/{n}", b"x") for n in names])
    await env.runtime.write_files([(f"{env.root}/sub/inner.txt", b"y")])


@pytest.mark.asyncio
async def test_list_dir_returns_every_entry_verbatim(env):
    await _seed(env, _ODD_NAMES)

    entries = await env.runtime.list_dir(env.root)

    assert sorted(e.name for e in entries) == sorted([*_ODD_NAMES, "sub"])
    by_name = {e.name: e for e in entries}
    assert by_name["sub"].is_dir is True
    assert by_name["line\nbreak.txt"].is_dir is False
    assert by_name["a b.txt"].path == f"{env.root}/a b.txt"


@pytest.mark.asyncio
async def test_list_dir_missing_is_not_found(env):
    missing = f"{env.root}/nope"
    with pytest.raises(SandboxNotFound) as ei:
        await env.runtime.list_dir(missing)
    assert ei.value.path == missing


@pytest.mark.asyncio
async def test_list_dir_on_file_is_not_a_directory(env):
    await _seed(env, ["f.txt"])
    with pytest.raises(SandboxNotADirectory):
        await env.runtime.list_dir(f"{env.root}/f.txt")


@pytest.mark.asyncio
async def test_read_file_roundtrip_and_missing(env):
    await env.runtime.write_files([(f"{env.root}/b.bin", b"\x00\xff\n\n")])

    assert await env.runtime.read_file(f"{env.root}/b.bin") == b"\x00\xff\n\n"
    with pytest.raises(SandboxNotFound):
        await env.runtime.read_file(f"{env.root}/nope.bin")


@pytest.mark.asyncio
async def test_run_output_is_verbatim(env):
    if not env.real_shell:
        pytest.skip("需要真实 shell")
    result = await env.runtime.run(
        "printf 'a\\n\\nb'; sleep 0.2; printf 'c\\n'; printf 'tail-no-nl'", cwd="/"
    )
    assert result.output == "a\n\nbc\ntail-no-nl"
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_run_large_output_is_complete(env):
    if not env.real_shell:
        pytest.skip("需要真实 shell")
    result = await env.runtime.run(
        'python3 -c "import sys\nfor i in range(50000): print(i)"', cwd="/"
    )
    lines = result.output.split("\n")
    assert lines[-1] == ""
    assert lines[:-1] == [str(i) for i in range(50000)]
