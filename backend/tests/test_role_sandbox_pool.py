"""RoleSandboxPool：v1→v2 迁移、角色隔离、跨角色不 interrupt。"""

from __future__ import annotations

import json

import pytest

from app.config import Settings
from app.engine.agent.tools import ToolRegistry
from app.engine.conversations import ConversationStore
from app.engine.organizer import Organizer
from app.engine.pending import PendingStore
from app.engine.retriever import Retriever
from app.engine.roles import DEFAULT_ROLE_ID, RoleStore
from app.engine.sandbox import state as sandbox_state
from app.engine.sandbox.fake_runtime import FakeSandboxRuntime
from app.engine.sandbox.naming import volume_name_for_role, volume_slug
from app.engine.sandbox.role_pool import RoleSandboxPool
from app.engine.sandbox.workspace_cwd import default_sandbox_cwd, resolve_sandbox_cwd
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import WebSearch
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.revision import IndexRevision
from app.index.vector import VectorIndex
from app.models.cooldown import CooldownStore
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


def _fake_factory(role_id: str, slot: dict) -> FakeSandboxRuntime:
    return FakeSandboxRuntime(sandbox_id=f"fake-{role_id}", role_id=role_id)


def _pool(tmp_path, **kwargs) -> RoleSandboxPool:
    return RoleSandboxPool(
        kb_path=tmp_path,
        runtime_factory=_fake_factory,
        default_volume="lorechat-sandbox-workspace",
        **kwargs,
    )


def _registry_with_pool(tmp_path, pool: RoleSandboxPool, conversations=None):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(embed_dim=8)
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm, index_revision=IndexRevision(tmp_path / "rev.txt"))
    pending = PendingStore(tmp_path / "knowledge" / ".kb" / "pending.json")
    settings = Settings(kb_path=tmp_path / "knowledge")
    writer = make_writer(repo, tmp_path)
    org = Organizer(
        repo=repo, retriever=retr, pending=pending, llm=llm, knowledge_writer=writer
    )
    return ToolRegistry(
        retr,
        repo,
        org,
        WebFetcher(),
        WebSearch(
            settings,
            cooldown=CooldownStore(settings.kb_path / ".kb" / "search_cd.json"),
        ),
        pending,
        writer,
        indexer=idx,
        conversations=conversations,
        sandbox_pool=pool,
    )


def test_volume_slug_docker_safe():
    assert volume_slug("default") == "default"
    assert volume_slug("Role A!") == "role-a"
    assert volume_slug("123abc").startswith("r-")
    long_id = "x" * 80
    slug = volume_slug(long_id)
    assert len(slug) <= 40
    assert volume_name_for_role("default") == "lorechat-sandbox-workspace"
    assert volume_name_for_role("analyst").startswith("lorechat-sandbox-ws-")


def test_migrate_v1_to_v2_keeps_disk_binding(tmp_path):
    path = sandbox_state.state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"sandbox_id": "old-sb-1", "mirror_region": "cn"}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    data = sandbox_state.ensure_migrated(tmp_path)
    assert data["version"] == 2
    assert data["migrated_from_v1"] is True
    slot = data["slots"][DEFAULT_ROLE_ID]
    assert slot["sandbox_id"] == "old-sb-1"
    assert slot["volume_name"] == "lorechat-sandbox-workspace"
    assert slot["mirror_region"] == "cn"
    assert sandbox_state.load_sandbox_id(tmp_path) == "old-sb-1"

    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["version"] == 2
    assert "sandbox_id" not in written or written.get("sandbox_id") != "old-sb-1"
    assert written["slots"][DEFAULT_ROLE_ID]["sandbox_id"] == "old-sb-1"


def test_clear_default_slot_keeps_other_roles(tmp_path):
    sandbox_state.upsert_slot(
        tmp_path, DEFAULT_ROLE_ID, sandbox_id="def-1", volume_name="lorechat-sandbox-workspace"
    )
    sandbox_state.upsert_slot(
        tmp_path, "other", sandbox_id="oth-1", volume_name="lorechat-sandbox-ws-other"
    )
    sandbox_state.clear_sandbox_id(tmp_path)
    assert sandbox_state.load_sandbox_id(tmp_path) is None
    other = sandbox_state.get_slot(tmp_path, "other")
    assert other is not None
    assert other["sandbox_id"] == "oth-1"
    default = sandbox_state.get_slot(tmp_path, DEFAULT_ROLE_ID)
    assert default is not None
    assert default["volume_name"] == "lorechat-sandbox-workspace"


def test_default_cwd_conversation_and_schedule():
    assert default_sandbox_cwd() == "/workspace"
    assert default_sandbox_cwd(conversation_id="cid-1") == "/workspace/conversations/cid-1"
    assert default_sandbox_cwd(schedule_id="sch-9") == "/workspace/schedules/sch-9"
    err = resolve_sandbox_cwd({"cwd": "/etc"})
    assert isinstance(err, dict)
    assert err.get("error") == "cwd not under /workspace"
    assert resolve_sandbox_cwd({"cwd": "/workspace/out"}) == "/workspace/out"


@pytest.mark.asyncio
async def test_pool_isolates_workspace_per_role(tmp_path):
    pool = _pool(tmp_path)
    rt_a = await pool.get("role-a")
    rt_b = await pool.get("role-b")
    assert rt_a is not rt_b
    await rt_a.write_file("/workspace/secret.txt", b"from-a")
    await rt_b.write_file("/workspace/secret.txt", b"from-b")
    assert await rt_a.read_file("/workspace/secret.txt") == b"from-a"
    assert await rt_b.read_file("/workspace/secret.txt") == b"from-b"
    bind_a = pool.binding("role-a")
    bind_b = pool.binding("role-b")
    assert bind_a is not None and bind_b is not None
    assert bind_a["volume_name"] != bind_b["volume_name"]
    assert bind_a["sandbox_id"] == "fake-role-a"
    assert bind_b["sandbox_id"] == "fake-role-b"


@pytest.mark.asyncio
async def test_interrupt_role_a_does_not_stop_b(tmp_path):
    pool = _pool(tmp_path)
    rt_a = await pool.get("alpha")
    rt_b = await pool.get("beta")
    eid_a = await rt_a.start_job("__stream_echo__")
    eid_b = await rt_b.start_job("__stream_echo__")
    await pool.interrupt_role("alpha")
    st_a = await rt_a.poll_job(eid_a)
    st_b = await rt_b.poll_job(eid_b)
    assert st_a.running is False
    assert st_a.exit_code == -1
    assert st_b.running is True


@pytest.mark.asyncio
async def test_tools_stop_conversation_does_not_cross_role(tmp_path):
    conv = ConversationStore(tmp_path / "c.db")
    roles = RoleStore(tmp_path / "r.db")
    other = roles.create(name="分析")
    cid_a = conv.create(role_id=DEFAULT_ROLE_ID)
    cid_b = conv.create(role_id=other["id"])
    pool = _pool(tmp_path)
    registry = _registry_with_pool(tmp_path, pool, conversations=conv)
    registry.sandbox.execution_engine.poll_interval_sec = 0.05

    run_a = await registry.execute(
        "sandbox_run",
        {"command": "__stream_echo__", "wait_sec": 0.12, "confirmed": True},
        conversation_id=cid_a,
    )
    run_b = await registry.execute(
        "sandbox_run",
        {"command": "__stream_echo__", "wait_sec": 0.12, "confirmed": True},
        conversation_id=cid_b,
    )
    assert run_a.get("running") is True
    assert run_b.get("running") is True
    await registry.interrupt_runtime(conversation_id=cid_a)
    st_a = await registry.execute(
        "sandbox_job_status", {"execution_id": run_a["execution_id"]}, conversation_id=cid_a
    )
    st_b = await registry.execute(
        "sandbox_job_status", {"execution_id": run_b["execution_id"]}, conversation_id=cid_b
    )
    assert st_a.get("running") is False
    assert st_b.get("running") is True


@pytest.mark.asyncio
async def test_interactive_cwd_defaults_under_conversation(tmp_path):
    conv = ConversationStore(tmp_path / "c.db")
    cid = conv.create(role_id=DEFAULT_ROLE_ID)
    pool = _pool(tmp_path)
    registry = _registry_with_pool(tmp_path, pool, conversations=conv)
    exec_rt = await pool.get(DEFAULT_ROLE_ID)
    await registry.execute(
        "sandbox_run",
        {"command": "echo hello", "confirmed": True},
        conversation_id=cid,
    )
    assert exec_rt.last_cwd == f"/workspace/conversations/{cid}"


@pytest.mark.asyncio
async def test_schedule_cwd_and_confirm_payload(tmp_path):
    conv = ConversationStore(tmp_path / "c.db")
    cid = conv.create(role_id=DEFAULT_ROLE_ID)
    pool = _pool(tmp_path)
    registry = _registry_with_pool(tmp_path, pool, conversations=conv)
    registry.sandbox.trust_mode = False
    gated = await registry.execute(
        "sandbox_run",
        {"command": "pip install foo", "schedule_id": "sched-1"},
        conversation_id=cid,
    )
    assert gated.get("awaiting_user") is True
    qid = gated["question_id"]
    payload = registry.pending.get(qid)["payload"]
    assert payload["role_id"] == DEFAULT_ROLE_ID
    assert payload["conversation_id"] == cid
    assert payload["schedule_id"] == "sched-1"
    assert payload["cwd"] == "/workspace/schedules/sched-1"
