"""沙箱工具与 FakeRuntime 单测。"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.engine.agent.prompts import MODE_DEFAULT, MODE_NO_WRITE
from app.engine.agent.tool_catalog import SANDBOX_TOOLS, select_tools
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
        WebSearch(settings),
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
    assert "a.txt" in listed["summary"]


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
async def test_publish_binary_attachment_roundtrip(tmp_path):
    registry, runtime = _make_registry(tmp_path)
    assert runtime is not None
    png = b"\x89PNG\r\n\x1a\n" + bytes(range(256))
    await runtime.write_file("/workspace/shot.png", png)
    pub = await registry.execute(
        "publish_from_sandbox",
        {
            "sandbox_path": "/workspace/shot.png",
            "directory": "图",
            "filename": "shot.png",
        },
    )
    assert pub.get("error") is None, pub
    assert pub.get("kind") == "attachment"
    assert pub.get("rel_path") == "图/attachments/shot.png"
    abs_p = registry.repo.abs_path(pub["rel_path"])
    assert abs_p.read_bytes() == png


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
