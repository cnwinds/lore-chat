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
from app.engine.sandbox.role_pool import RoleSandboxPool, SandboxPoolFullError
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
    assert "角色" in gated.get("question", "")
    assert payload.get("role_id") == DEFAULT_ROLE_ID


@pytest.mark.asyncio
async def test_pool_rejects_when_full_and_no_idle(tmp_path):
    pool = _pool(tmp_path, max_roles=2, idle_ttl_sec=3600)
    rt_a = await pool.get("a")
    rt_b = await pool.get("b")
    with pytest.raises(Exception) as ei:
        await pool.get("c")
    from app.engine.sandbox.role_pool import SandboxPoolFullError

    assert ei.type is SandboxPoolFullError
    assert "沙箱池已满" in str(ei.value)
    assert pool.peek("c") is None
    assert pool.peek("a") is rt_a
    assert pool.peek("b") is rt_b
    assert rt_a is not rt_b


@pytest.mark.asyncio
async def test_tools_pool_full_returns_chinese_error(tmp_path):
    conv = ConversationStore(tmp_path / "c.db")
    roles = RoleStore(tmp_path / "r.db")
    extra = roles.create(name="分析")
    cid = conv.create(role_id=extra["id"])
    pool = _pool(tmp_path, max_roles=1, idle_ttl_sec=3600)
    await pool.get(DEFAULT_ROLE_ID)
    registry = _registry_with_pool(tmp_path, pool, conversations=conv)
    out = await registry.execute(
        "sandbox_run",
        {"command": "echo hi", "confirmed": True},
        conversation_id=cid,
    )
    assert out.get("error") == "sandbox_pool_full"
    assert "沙箱池已满" in out.get("summary", "")
    assert pool.peek(extra["id"]) is None
    assert pool.peek(DEFAULT_ROLE_ID) is not None


@pytest.mark.asyncio
async def test_idle_reclaim_destroys_container_keeps_volume(tmp_path):
    pool = _pool(tmp_path, max_roles=1, idle_ttl_sec=0.05)
    rt_a = await pool.get("alpha")
    vol_a = pool.binding("alpha")["volume_name"]
    sid_a = pool.binding("alpha")["sandbox_id"]
    pool._last_used["alpha"] = pool._last_used["alpha"] - 10
    rt_b = await pool.get("beta")
    assert rt_b is not rt_a
    assert rt_a.destroy_calls
    assert rt_a.destroy_calls[-1]["keep_volume"] is True
    assert rt_a.container_alive is False
    assert pool.peek("alpha") is None
    slot_a = pool.binding("alpha")
    assert slot_a is not None
    assert slot_a["volume_name"] == vol_a
    assert slot_a.get("sandbox_id") in (None, "")
    assert slot_a.get("reclaimable") is True
    assert pool.binding("beta")["sandbox_id"] != sid_a


@pytest.mark.asyncio
async def test_busy_slot_not_reclaimed_at_cap(tmp_path):
    pool = _pool(tmp_path, max_roles=1, idle_ttl_sec=0.01)
    rt_a = await pool.get("busy")
    await rt_a.start_job("__stream_echo__")
    pool._last_used["busy"] = pool._last_used["busy"] - 10
    from app.engine.sandbox.role_pool import SandboxPoolFullError

    with pytest.raises(SandboxPoolFullError):
        await pool.get("other")
    assert pool.peek("busy") is rt_a
    assert rt_a.container_alive is True


@pytest.mark.asyncio
async def test_release_role_keeps_volume_by_default(tmp_path):
    pool = _pool(tmp_path, max_roles=4)
    rt = await pool.get("doomed")
    vol = pool.binding("doomed")["volume_name"]
    await rt.start_job("__stream_echo__")
    await pool.release_role("doomed")
    assert pool.peek("doomed") is None
    slot = pool.binding("doomed")
    assert slot is not None
    assert slot["volume_name"] == vol
    assert slot.get("reclaimable") is True
    assert not slot.get("sandbox_id")
    assert rt.destroy_calls[-1]["keep_volume"] is True


@pytest.mark.asyncio
async def test_release_role_can_drop_volume_binding(tmp_path):
    pool = _pool(tmp_path, destroy_volume_on_role_delete=True)
    await pool.get("gone")
    await pool.release_role("gone")
    assert pool.binding("gone") is None


@pytest.mark.asyncio
async def test_reclaim_idle_without_new_get(tmp_path):
    pool = _pool(tmp_path, idle_ttl_sec=0.05)
    rt = await pool.get("idle-me")
    vol = pool.binding("idle-me")["volume_name"]
    pool._last_used["idle-me"] = pool._last_used["idle-me"] - 10
    gone = await pool.reclaim_idle()
    assert "idle-me" in gone
    assert pool.peek("idle-me") is None
    assert pool.binding("idle-me")["volume_name"] == vol
    assert rt.container_alive is False


def test_pool_snapshot_counts(tmp_path):
    pool = _pool(tmp_path, max_roles=4)
    snap = pool.pool_snapshot()
    assert snap["max"] == 4
    assert snap["active"] == 0
    assert snap["busy_roles"] == []
    assert snap["api_max"] == 8
    assert snap["api_active"] == 0


@pytest.mark.asyncio
async def test_api_roles_do_not_consume_sidebar_cap(tmp_path):
    pool = _pool(tmp_path, max_roles=1, max_api_roles=2)
    sidebar = await pool.get("researcher")
    api_a = await pool.get("api_aaa111")
    api_b = await pool.get("api_bbb222")
    assert sidebar is not api_a
    assert api_a is not api_b
    snap = pool.pool_snapshot()
    assert snap["active"] == 1
    assert snap["api_active"] == 2
    with pytest.raises(SandboxPoolFullError):
        await pool.get("another-sidebar")
    with pytest.raises(SandboxPoolFullError):
        await pool.get("api_ccc333")


@pytest.mark.asyncio
async def test_existing_live_role_get_at_cap(tmp_path):
    pool = _pool(tmp_path, max_roles=1)
    first = await pool.get("only")
    again = await pool.get("only")
    assert first is again
    snap = pool.pool_snapshot()
    assert snap["active"] == 1
    assert snap["max"] == 1
