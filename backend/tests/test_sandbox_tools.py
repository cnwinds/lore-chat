"""沙箱工具与 FakeRuntime 单测。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.models.cooldown import CooldownStore
from app.engine.agent.tool_catalog import SANDBOX_TOOLS, select_tools
from app.engine.agent.prompts import MODE_DEFAULT, MODE_NO_WRITE
from app.engine.agent.tools import ToolRegistry
from app.engine.organizer import Organizer
from app.engine.pending import PendingStore
from app.engine.retriever import Retriever
from app.engine.sandbox.fake_runtime import FakeSandboxRuntime
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import WebSearch
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.revision import IndexRevision
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


def _tool_names(defs):
    return {d["function"]["name"] for d in defs}


def _make_registry(tmp_path, *, sandbox=True):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(embed_dim=8)
    idx = Indexer(vi, fi, llm)
    rev = IndexRevision(tmp_path / "revision.txt")
    retr = Retriever(vi, fi, llm, index_revision=rev)
    pending = PendingStore(tmp_path / "knowledge" / ".kb" / "pending.json")
    settings = Settings(kb_path=tmp_path / "knowledge")
    writer = make_writer(repo, tmp_path)
    org = Organizer(
        repo=repo,
        retriever=retr,
        pending=pending,
        llm=llm,
        knowledge_writer=writer,
    )
    runtime = FakeSandboxRuntime() if sandbox else None
    registry = ToolRegistry(
        retr,
        repo,
        org,
        WebFetcher(),
        WebSearch(settings, cooldown=CooldownStore(settings.kb_path / '.kb' / 'search_cd.json')),
        pending,
        writer,
        indexer=idx,
        sandbox_runtime=runtime,
    )
    return registry, runtime


def test_select_tools_hides_sandbox_by_default():
    names = _tool_names(select_tools(MODE_DEFAULT, web_enabled=True))
    assert SANDBOX_TOOLS.isdisjoint(names)


def test_select_tools_includes_sandbox_when_enabled():
    names = _tool_names(
        select_tools(MODE_DEFAULT, web_enabled=True, sandbox_enabled=True)
    )
    assert SANDBOX_TOOLS <= names
    assert "sandbox_job_status" in names
    assert "sandbox_stop" in names


def test_select_tools_no_write_drops_publish():
    names = _tool_names(
        select_tools(MODE_NO_WRITE, web_enabled=True, sandbox_enabled=True)
    )
    assert "publish_from_sandbox" not in names
    assert "sandbox_run" in names


@pytest.mark.asyncio
async def test_sandbox_run_and_list(tmp_path):
    registry, runtime = _make_registry(tmp_path)
    assert runtime is not None
    r = await registry.execute("sandbox_run", {"command": "echo hello"})
    assert r["exit_code"] == 0
    assert "hello" in r["summary"]

    await registry.execute(
        "sandbox_run",
        {"command": "mkdir -p /workspace/out && echo hi > /workspace/out/a.txt"},
    )
    listed = await registry.execute("sandbox_list_dir", {"path": "/workspace/out"})
    assert listed["count"] == 1
    assert listed["summary"] == "/workspace/out 共 1 项；路径见 entries"
    assert "\n" not in listed["summary"]
    assert listed["entries"] == [
        {
            "name": "a.txt",
            "path": "/workspace/out/a.txt",
            "is_dir": False,
            "kind": "file",
        }
    ]


@pytest.mark.asyncio
async def test_sandbox_read_and_publish(tmp_path):
    registry, runtime = _make_registry(tmp_path)
    assert runtime is not None
    await runtime.write_file("/workspace/note.md", b"# Title\nhello sandbox\n")
    read = await registry.execute(
        "sandbox_read_file", {"path": "/workspace/note.md"}
    )
    assert "hello sandbox" in (read.get("content") or "")

    pub = await registry.execute(
        "publish_from_sandbox",
        {
            "sandbox_path": "/workspace/note.md",
            "directory": "备忘",
            "filename": "from-sandbox.md",
        },
    )
    assert pub.get("rel_path") == "备忘/from-sandbox.md"
    assert any(s.get("path") == "备忘/from-sandbox.md" for s in pub["sources"])


@pytest.mark.asyncio
async def test_publish_from_sandbox_batch(tmp_path):
    registry, runtime = _make_registry(tmp_path)
    assert runtime is not None
    await runtime.write_file("/workspace/a.md", b"# A\n")
    await runtime.write_file("/workspace/out/b.sh", b"#!/bin/sh\necho hi\n")
    pub = await registry.execute(
        "publish_from_sandbox",
        {
            "files": [
                {
                    "sandbox_path": "/workspace/a.md",
                    "directory": "备忘",
                    "filename": "a.md",
                },
                {
                    "sandbox_path": "/workspace/out/b.sh",
                    "directory": "scripts",
                    "filename": "b.sh",
                },
            ]
        },
    )
    assert pub.get("ok") == 2
    assert pub.get("failed") == 0
    assert pub.get("error") is None
    paths = {it["rel_path"] for it in pub["items"]}
    assert paths == {"备忘/a.md", "scripts/b.sh"}
    assert registry.repo.abs_path("备忘/a.md").is_file()
    assert b"echo hi" in registry.repo.abs_path("scripts/b.sh").read_bytes()


@pytest.mark.asyncio
async def test_publish_from_sandbox_batch_partial(tmp_path):
    registry, runtime = _make_registry(tmp_path)
    assert runtime is not None
    await runtime.write_file("/workspace/ok.md", b"# ok\n")
    pub = await registry.execute(
        "publish_from_sandbox",
        {
            "files": [
                {
                    "sandbox_path": "/workspace/ok.md",
                    "directory": "备忘",
                    "filename": "ok.md",
                },
                {
                    "sandbox_path": "/workspace/missing.md",
                    "directory": "备忘",
                    "filename": "missing.md",
                },
            ]
        },
    )
    assert pub.get("ok") == 1
    assert pub.get("failed") == 1
    assert pub.get("error")
    by_sp = {it["sandbox_path"]: it for it in pub["items"]}
    assert by_sp["/workspace/ok.md"]["ok"] is True
    assert by_sp["/workspace/missing.md"]["error"] == "not found"


@pytest.mark.asyncio
async def test_publish_allows_binary(tmp_path):
    """Agent publish：沙箱任意二进制（含视频）可入库。"""
    registry, runtime = _make_registry(tmp_path)
    assert runtime is not None
    blob = b"\x00\x01\x02\xff" + bytes(range(64))
    mp4 = b"\x00\x00\x00\x18ftypmp42" + bytes(range(32))
    await runtime.write_file("/workspace/blob.bin", blob)
    await runtime.write_file("/workspace/out/report.mp4", mp4)
    pub = await registry.execute(
        "publish_from_sandbox",
        {
            "files": [
                {
                    "sandbox_path": "/workspace/blob.bin",
                    "directory": "备忘",
                    "filename": "blob.bin",
                },
                {
                    "sandbox_path": "/workspace/out/report.mp4",
                    "directory": "备忘/HN视频0816",
                    "filename": "report.mp4",
                },
            ]
        },
    )
    assert pub.get("ok") == 2, pub
    assert pub.get("failed") == 0
    assert pub.get("error") is None
    assert registry.repo.abs_path("备忘/blob.bin").read_bytes() == blob
    assert (
        registry.repo.abs_path("备忘/HN视频0816/report.mp4").read_bytes() == mp4
    )


@pytest.mark.asyncio
async def test_publish_image_png_and_svg_as_attachments(tmp_path):
    """PNG/SVG 与位图同轨：可 publish，并挂 attachments 供聊天预览。"""
    from app.storage.kb_media_paths import media_generated_dir

    registry, runtime = _make_registry(tmp_path)
    assert runtime is not None
    png = b"\x89PNG\r\n\x1a\n" + bytes(range(32))
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="10"/></svg>\n'
    await runtime.write_file("/workspace/shot.png", png)
    await runtime.write_file("/workspace/logo.svg", svg)
    gen_dir = media_generated_dir()
    pub = await registry.execute(
        "publish_from_sandbox",
        {
            "files": [
                {
                    "sandbox_path": "/workspace/shot.png",
                    "directory": gen_dir,
                    "filename": "shot.png",
                },
                {
                    "sandbox_path": "/workspace/logo.svg",
                    "directory": gen_dir,
                    "filename": "logo.svg",
                },
            ]
        },
    )
    assert pub.get("ok") == 2, pub
    assert pub.get("failed") == 0
    assert pub.get("attachments") == [
        f"{gen_dir}/shot.png",
        f"{gen_dir}/logo.svg",
    ]
    assert registry.repo.abs_path(f"{gen_dir}/shot.png").read_bytes() == png
    written_svg = registry.repo.abs_path(f"{gen_dir}/logo.svg").read_text(
        encoding="utf-8"
    )
    assert written_svg.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert '<svg xmlns="http://www.w3.org/2000/svg">' in written_svg


@pytest.mark.asyncio
async def test_publish_text_asset_roundtrip(tmp_path):
    registry, runtime = _make_registry(tmp_path)
    assert runtime is not None
    body = b"print('hi')\n"
    await runtime.write_file("/workspace/run.py", body)
    pub = await registry.execute(
        "publish_from_sandbox",
        {
            "sandbox_path": "/workspace/run.py",
            "directory": "scripts",
            "filename": "run.py",
        },
    )
    assert pub.get("error") is None, pub
    assert pub.get("kind") == "file"
    assert pub.get("rel_path") == "scripts/run.py"
    assert registry.repo.abs_path(pub["rel_path"]).read_bytes() == body


@pytest.mark.asyncio
async def test_publish_rejects_outside_workspace(tmp_path):
    registry, _ = _make_registry(tmp_path)
    r = await registry.execute(
        "publish_from_sandbox",
        {
            "sandbox_path": "/etc/passwd",
            "directory": "备忘",
            "filename": "x.md",
        },
    )
    assert r.get("error") == "path not under /workspace"


@pytest.mark.asyncio
async def test_sandbox_disabled_errors(tmp_path):
    registry, _ = _make_registry(tmp_path, sandbox=False)
    r = await registry.execute("sandbox_run", {"command": "echo x"})
    assert r.get("error")


@pytest.mark.asyncio
async def test_sandbox_run_uses_execution_engine(tmp_path):
    registry, _ = _make_registry(tmp_path)
    exec_spy = AsyncMock(wraps=registry.sandbox.execution_engine.execute)
    registry.sandbox.execution_engine.execute = exec_spy  # type: ignore[method-assign]

    await registry.execute(
        "sandbox_run",
        {"command": "echo hi", "wait_sec": 30, "confirmed": True},
    )

    exec_spy.assert_awaited_once()
    kwargs = exec_spy.await_args.kwargs
    assert kwargs["wait_sec"] == 30
    assert kwargs["if_exceeded"] == "return"
    assert kwargs["command"] == "echo hi"


@pytest.mark.asyncio
async def test_python_command_gets_unbuffer_env(tmp_path):
    registry, _ = _make_registry(tmp_path)
    exec_spy = AsyncMock(wraps=registry.sandbox.execution_engine.execute)
    registry.sandbox.execution_engine.execute = exec_spy  # type: ignore[method-assign]

    await registry.execute(
        "sandbox_run",
        {"command": "/venv/bin/python script.py", "confirmed": True},
    )

    cmd = exec_spy.await_args.kwargs["command"]
    assert cmd.startswith("PYTHONUNBUFFERED=1 ")
    assert "/venv/bin/python script.py" in cmd


@pytest.mark.asyncio
async def test_sandbox_run_checkpoint_on_wait_exceeded(tmp_path):
    registry, _ = _make_registry(tmp_path)
    registry.sandbox.execution_engine.poll_interval_sec = 0.05

    r = await registry.execute(
        "sandbox_run",
        {"command": "__stream_echo__", "wait_sec": 0.15, "confirmed": True},
    )
    assert r.get("checkpoint") is True
    assert r.get("running") is True
    assert r.get("wait_exceeded") is True
    eid = r.get("execution_id")
    assert eid
    assert "line" in (r.get("stdout") or "")


@pytest.mark.asyncio
async def test_sandbox_run_attach_and_complete(tmp_path):
    registry, _ = _make_registry(tmp_path)
    registry.sandbox.execution_engine.poll_interval_sec = 0.05

    first = await registry.execute(
        "sandbox_run",
        {"command": "__stream_echo__", "wait_sec": 0.12, "confirmed": True},
    )
    eid = first["execution_id"]
    assert first.get("running") is True

    done = await registry.execute(
        "sandbox_run",
        {
            "execution_id": eid,
            "if_exceeded": "wait_until_done",
            "confirmed": True,
        },
    )
    assert done.get("running") is False
    assert done.get("exit_code") == 0
    assert "line4" in (done.get("stdout") or "")


@pytest.mark.asyncio
async def test_sandbox_stop(tmp_path):
    registry, _ = _make_registry(tmp_path)
    registry.sandbox.execution_engine.poll_interval_sec = 0.05

    running = await registry.execute(
        "sandbox_run",
        {"command": "__stream_echo__", "wait_sec": 0.12, "confirmed": True},
    )
    eid = running["execution_id"]
    stopped = await registry.execute("sandbox_stop", {"execution_id": eid})
    assert stopped.get("stopped") is True
    assert stopped.get("running") is False


@pytest.mark.asyncio
async def test_sandbox_run_if_exceeded_stop(tmp_path):
    registry, _ = _make_registry(tmp_path)
    registry.sandbox.execution_engine.poll_interval_sec = 0.05

    r = await registry.execute(
        "sandbox_run",
        {
            "command": "__stream_echo__",
            "wait_sec": 0.12,
            "if_exceeded": "stop",
            "confirmed": True,
        },
    )
    assert r.get("stopped") is True
    assert r.get("running") is False
