"""沙箱确认策略与 confirm 门。"""

from __future__ import annotations

import pytest

from app.engine.organizer import Organizer
from app.models.cooldown import CooldownStore
from app.engine.pending import PendingStore
from app.engine.retriever import Retriever
from app.engine.sandbox.fake_runtime import FakeSandboxRuntime
from app.engine.sandbox.policy import command_needs_confirmation
from app.engine.agent.tools import ToolRegistry
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import WebSearch
from app.config import Settings
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.revision import IndexRevision
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


@pytest.mark.parametrize(
    "cmd,need",
    [
        ("ls /workspace", False),
        ("echo hi", False),
        ("cat /workspace/a.md", False),
        ("mkdir -p /workspace/x", False),
        ("pip install edge-tts", True),
        ("rm -rf /", True),
        ("python script.py", True),
        ("apt-get update && apt-get install -y ffmpeg", True),
        ("ls && pip install x", True),
    ],
)
def test_command_needs_confirmation(cmd, need):
    assert command_needs_confirmation(cmd) is need


def _make_org(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    pending = PendingStore(tmp_path / "knowledge" / ".kb" / "pending.json")
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(embed_dim=8)
    retr = Retriever(vi, fi, llm, index_revision=IndexRevision(tmp_path / "rev.txt"))
    writer = make_writer(repo, tmp_path)
    org = Organizer(
        repo=repo, retriever=retr, pending=pending, llm=llm, knowledge_writer=writer
    )
    return org, pending


def test_resolve_sandbox_confirm_approve(tmp_path):
    from app.engine.sandbox.command_gate import SandboxCommandGate

    _, pending = _make_org(tmp_path)
    gate = SandboxCommandGate(pending, trust_mode=False)
    qid = pending.create(
        "run?",
        [{"id": "approve", "label": "执行"}, {"id": "deny", "label": "取消"}],
        {
            "kind": "sandbox_confirm",
            "command": "pip install edge-tts",
            "cwd": "/workspace",
            "background": False,
            "wait_sec": 60,
            "if_exceeded": "return",
        },
    )
    result = gate.resolve(qid, ["approve"])
    assert result.status == "sandbox_execute"
    assert result.sandbox_run_args is not None
    assert result.sandbox_run_args["command"] == "pip install edge-tts"
    assert result.sandbox_run_args["confirmed"] is True


def test_resolve_sandbox_confirm_deny(tmp_path):
    from app.engine.sandbox.command_gate import SandboxCommandGate

    _, pending = _make_org(tmp_path)
    gate = SandboxCommandGate(pending, trust_mode=False)
    qid = pending.create(
        "run?",
        [{"id": "approve", "label": "执行"}, {"id": "deny", "label": "取消"}],
        {"kind": "sandbox_confirm", "command": "rm -rf /"},
    )
    result = gate.resolve(qid, ["deny"])
    assert result.status == "acknowledged"
    assert "取消" in result.message


def _registry(tmp_path, *, trust=False):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    pending = PendingStore(tmp_path / "knowledge" / ".kb" / "pending.json")
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(embed_dim=8)
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm, index_revision=IndexRevision(tmp_path / "rev.txt"))
    settings = Settings(kb_path=tmp_path / "knowledge")
    writer = make_writer(repo, tmp_path)
    org = Organizer(
        repo=repo, retriever=retr, pending=pending, llm=llm, knowledge_writer=writer
    )
    reg = ToolRegistry(
        retr,
        repo,
        org,
        WebFetcher(),
        WebSearch(settings, cooldown=CooldownStore(settings.kb_path / '.kb' / 'search_cd.json')),
        pending,
        writer,
        indexer=idx,
        sandbox_runtime=FakeSandboxRuntime(),
    )
    reg.sandbox.trust_mode = trust
    return reg, pending


@pytest.mark.asyncio
async def test_sandbox_run_gates_risky_command(tmp_path):
    reg, pending = _registry(tmp_path, trust=False)
    r = await reg.execute("sandbox_run", {"command": "pip install foo"})
    assert r.get("awaiting_user") is True
    assert r.get("question_id")
    assert pending.get(r["question_id"])["payload"]["kind"] == "sandbox_confirm"


@pytest.mark.asyncio
async def test_sandbox_run_safe_command_no_gate(tmp_path):
    reg, _ = _registry(tmp_path, trust=False)
    r = await reg.execute("sandbox_run", {"command": "echo hello"})
    assert r.get("exit_code") == 0
    assert "hello" in r["summary"]


@pytest.mark.asyncio
async def test_sandbox_run_trust_mode_skips_gate(tmp_path):
    reg, _ = _registry(tmp_path, trust=True)
    r = await reg.execute("sandbox_run", {"command": "pip install foo"})
    assert r.get("awaiting_user") is not True
    assert "ran:pip install foo" in r.get("summary", "") or r.get("exit_code") == 0


@pytest.mark.asyncio
async def test_sandbox_run_confirmed_skips_gate(tmp_path):
    reg, _ = _registry(tmp_path, trust=False)
    r = await reg.execute(
        "sandbox_run",
        {"command": "pip install foo", "confirmed": True},
    )
    assert r.get("awaiting_user") is not True


@pytest.mark.asyncio
async def test_sandbox_job_status(tmp_path):
    import asyncio

    reg, _ = _registry(tmp_path, trust=True)
    start = await reg.execute(
        "sandbox_run",
        {"command": "echo done", "if_exceeded": "wait_until_done", "confirmed": True},
    )
    eid = start.get("execution_id")
    assert eid
    for _ in range(40):
        st = await reg.execute("sandbox_job_status", {"execution_id": eid})
        if not st.get("running"):
            assert st.get("exit_code") == 0 or "done" in st.get("summary", "")
            return
        await asyncio.sleep(0.05)
    raise AssertionError("job did not finish")
