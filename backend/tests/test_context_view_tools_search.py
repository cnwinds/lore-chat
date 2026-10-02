"""ContextViewTools.search"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.engine.agent.prompts import MODE_API
from app.engine.agent.tool_catalog import select_tools
from app.engine.agent.tool_loop import AgentToolLoop
from app.engine.agent.tool_progress import ToolProgressExecutor
from app.engine.agent.tools import ToolRegistry
from app.engine.conversations import ConversationStore
from app.engine.organizer import Organizer
from app.engine.pending import PendingStore
from app.engine.retriever import Retriever
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import WebSearch
from app.index.message_chunk import MessageChunk
from app.models.cooldown import CooldownStore
from app.models.llm import FakeLLMClient, ToolCall
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_conversation_index, make_writer

def test_default_search_paths_owner_kb_and_dm(cv_env):
    cid = cv_env.conv.create(role_id="default")
    out = cv_env.tools.search({"query": "noop"}, conversation_id=cid)
    assert "paths" in out
    assert out["paths"][0] == "lore://kb/"
    assert "/dm/default/" in out["paths"][1]


def test_canonical_paths_tilde_and_bare_kb(cv_env):
    cid = cv_env.conv.create(role_id="default")
    out = cv_env.tools.search(
        {
            "query": "noop",
            "paths": ["lore://conversations/dm/~/", "笔记/草稿.md"],
        },
        conversation_id=cid,
    )
    assert out["paths"][0].endswith("/dm/default/")
    assert out["paths"][1] == "lore://kb/笔记/草稿.md"


def test_search_kb_dir_prefix_vs_exact_file(cv_env):
    cv_env.repo.write_doc(
        "技能/a.md",
        {"title": "a", "tags": [], "source": "t"},
        "# a\n\nprefix_only_token_xyz",
        commit_msg="t",
    )
    cv_env.repo.write_doc(
        "笔记.md",
        {"title": "n", "tags": [], "source": "t"},
        "# n\n\nexact_file_token_xyz",
        commit_msg="t",
    )
    cv_env.idx.reindex_doc("技能/a.md", "# a\n\nprefix_only_token_xyz")
    cv_env.idx.reindex_doc("笔记.md", "# n\n\nexact_file_token_xyz")
    out = cv_env.tools.search(
        {
            "query": "prefix_only_token_xyz",
            "paths": ["lore://kb/技能/", "lore://kb/笔记.md"],
            "k": 10,
        }
    )
    paths = {h.get("uri") for h in out.get("hits") or []}
    assert any("技能/a.md" in (u or "") for u in paths)
    out2 = cv_env.tools.search(
        {"query": "exact_file_token_xyz", "paths": ["lore://kb/笔记.md"]}
    )
    assert len(out2.get("hits") or []) >= 1


def test_search_multiple_paths_kb_and_other_role_dm(cv_env):
    rid = cv_env.roles.create(name="多路径", system_prompt="")["id"]
    cid = cv_env.conv.create(role_id=rid)
    cv_env.ci.upsert_message_chunks(
        conversation_id=cid,
        message_id="mm1",
        role="user",
        ts="2026-07-10T10:00:00",
        conversation_title="多路径",
        chunks=[MessageChunk(0, 0, 20, "multi_path_conv_hit")],
    )
    cv_env.repo.write_doc(
        "多路径/doc.md",
        {"title": "d", "tags": [], "source": "t"},
        "# d\n\nmulti_path_kb_hit",
        commit_msg="t",
    )
    cv_env.idx.reindex_doc("多路径/doc.md", "# d\n\nmulti_path_kb_hit")
    out = cv_env.tools.search(
        {
            "query": "multi_path",
            "paths": [f"lore://conversations/dm/{rid}/", "lore://kb/多路径/"],
            "k": 10,
        },
        conversation_id=cv_env.conv.create(role_id="default"),
    )
    types = {s.get("type") for s in out.get("sources", [])}
    assert "conversation" in types
    assert "kb" in types


def test_search_memory_root_owner_vs_channel(cv_env):
    cv_env.owner.remember("根路径记忆词", origin="explicit_remember")
    owner_cid = cv_env.conv.create(role_id="default")
    out_owner = cv_env.tools.search(
        {"query": "根路径", "paths": ["lore://memory/"]},
        conversation_id=owner_cid,
    )
    assert out_owner.get("error") != "out_of_scope"
    assert "memory" in out_owner

    role = cv_env.roles.create(name="通道用", system_prompt="")
    persona = cv_env.roles.create_persona(name="P", system_prompt="")
    inst = cv_env.channel_instances.create(
        type_id="script_api",
        name="ch",
        persona_id=persona["id"],
        role_id=role["id"],
    )
    ch_cid = cv_env.conv.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    out_ch = cv_env.tools.search(
        {"query": "根路径", "paths": ["lore://memory/"]},
        conversation_id=ch_cid,
    )
    assert out_ch.get("error") != "out_of_scope"
    assert len(out_ch.get("memory") or []) == 0


def test_unknown_conversation_id_not_found(cv_env):
    out = cv_env.tools.search({"query": "x"}, conversation_id="no-such-conversation")
    assert out.get("error") == "not_found"


def test_current_conversation_excluded_from_default_dm(cv_env):
    cid = cv_env.conv.create(role_id="default")
    t1 = cv_env.conv.begin_turn(
        cid, user_text="当前会话独有词 xyzzy_cur", client_message_id="c1"
    )
    cv_env.conv.finalize_turn(
        cid,
        t1["turn_id"],
        assistant={"text": "ok", "timeline": [], "sources": [], "status": "complete"},
    )
    other = cv_env.conv.create(role_id="default")
    t2 = cv_env.conv.begin_turn(other, user_text="其它 xyzzy_other", client_message_id="c2")
    cv_env.conv.finalize_turn(
        other,
        t2["turn_id"],
        assistant={"text": "ok", "timeline": [], "sources": [], "status": "complete"},
    )
    cv_env.ci.upsert_message_chunks(
        conversation_id=cid,
        message_id="m-cur",
        role="user",
        ts="2026-07-11T10:00:00",
        conversation_title="当前",
        chunks=[MessageChunk(0, 0, 12, "xyzzy_cur")],
    )
    cv_env.ci.upsert_message_chunks(
        conversation_id=other,
        message_id="m-other",
        role="user",
        ts="2026-07-10T10:00:00",
        conversation_title="其它",
        chunks=[MessageChunk(0, 0, 12, "xyzzy_other")],
    )
    out = cv_env.tools.search({"query": "xyzzy"}, conversation_id=cid)
    cids = {s.get("cid") for s in out.get("sources", []) if s.get("type") == "conversation"}
    assert cid not in cids


def test_explicit_other_role_dm_path(cv_env):
    rid = cv_env.roles.create(name="档案员", system_prompt="")["id"]
    cid = cv_env.conv.create(role_id=rid)
    t = cv_env.conv.begin_turn(cid, user_text="档案员会话 alpha123", client_message_id="a1")
    cv_env.conv.finalize_turn(
        cid,
        t["turn_id"],
        assistant={"text": "ok", "timeline": [], "sources": [], "status": "complete"},
    )
    cv_env.ci.upsert_message_chunks(
        conversation_id=cid,
        message_id="m-arch",
        role="user",
        ts="2026-07-10T10:00:00",
        conversation_title="档案",
        chunks=[MessageChunk(0, 0, 16, "alpha123")],
    )
    cur = cv_env.conv.create(role_id="default")
    out = cv_env.tools.search(
        {"query": "alpha123", "paths": [f"lore://conversations/dm/{rid}/"]},
        conversation_id=cur,
    )
    assert out.get("error") != "out_of_scope"
    assert any(s.get("cid") == cid for s in out.get("sources", []))


def test_channel_default_kb_only_out_of_scope_dm(cv_env):
    role = cv_env.roles.create(name="通道用", system_prompt="")
    persona = cv_env.roles.create_persona(name="P", system_prompt="")
    inst = cv_env.channel_instances.create(
        type_id="script_api",
        name="ch",
        persona_id=persona["id"],
        role_id=role["id"],
    )
    cid = cv_env.conv.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    out = cv_env.tools.search(
        {"query": "x", "paths": ["lore://conversations/dm/~/"]},
        conversation_id=cid,
    )
    assert out.get("error") == "out_of_scope"


def test_channel_memory_role_out_of_scope_persona_ok(cv_env):
    role = cv_env.roles.create(name="通道用", system_prompt="")
    persona = cv_env.roles.create_persona(name="P", system_prompt="")
    other_persona = cv_env.roles.create_persona(name="Other", system_prompt="")
    inst = cv_env.channel_instances.create(
        type_id="script_api",
        name="ch",
        persona_id=persona["id"],
        role_id=role["id"],
    )
    cid = cv_env.conv.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    assert (
        cv_env.tools.search(
            {"query": "x", "paths": ["lore://memory/role/"]},
            conversation_id=cid,
        ).get("error")
        == "out_of_scope"
    )
    assert (
        cv_env.tools.search(
            {"query": "x", "paths": [f"lore://memory/persona/{other_persona['id']}/"]},
            conversation_id=cid,
        ).get("error")
        == "out_of_scope"
    )
    ok = cv_env.tools.search(
        {"query": "x", "paths": ["lore://memory/persona/~/"]},
        conversation_id=cid,
    )
    assert ok.get("error") != "out_of_scope"


def test_channel_memory_owner_only_when_enabled(cv_env):
    role = cv_env.roles.create(name="通道用", system_prompt="")
    persona = cv_env.roles.create_persona(name="P", system_prompt="")
    inst = cv_env.channel_instances.create(
        type_id="script_api",
        name="ch",
        persona_id=persona["id"],
        role_id=role["id"],
    )
    cid = cv_env.conv.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    out = cv_env.tools.search(
        {"query": "x", "paths": ["lore://memory/owner/"]},
        conversation_id=cid,
    )
    assert out.get("error") == "out_of_scope"
    cv_env.channel_instances.update(inst["id"], include_owner_memory=True)
    out2 = cv_env.tools.search(
        {"query": "x", "paths": ["lore://memory/owner/"]},
        conversation_id=cid,
    )
    assert out2.get("error") != "out_of_scope"


def test_memory_interleave_and_kind_filter(cv_env):
    cv_env.owner.remember("偏好深色主题", origin="explicit_remember")
    cv_env.owner.remember("长期目标学 Rust", origin="explicit_remember")
    out = cv_env.tools.search(
        {
            "query": "主题",
            "paths": ["lore://memory/owner/preference/"],
        },
        conversation_id=cv_env.conv.create(role_id="default"),
    )
    mem = out.get("memory") or []
    assert len(mem) <= 10
    assert all(m.get("kind") == "preference" for m in mem)
    assert all("uri" in m and m["uri"].startswith("lore://memory/") for m in mem)


def test_hits_have_uri_and_kind(cv_env):
    path = "测试/uri.md"
    body = "# t\n\nunique_token_uri_kind"
    cv_env.repo.write_doc(
        path,
        {"title": "t", "tags": [], "source": "test"},
        body,
        commit_msg="test",
    )
    cv_env.idx.reindex_doc(path, body)
    out = cv_env.tools.search({"query": "unique_token_uri_kind"})
    for h in out.get("hits") or []:
        assert h.get("uri")
        assert h.get("kind")


def test_cursor_paging_and_binding(cv_env):
    token = "cursor_suite_shared"
    for i in range(15):
        p = f"游标批/page{i:02d}.md"
        body = f"# p{i}\n\n{token} doc{i:02d}"
        cv_env.repo.write_doc(
            p,
            {"title": f"p{i}", "tags": [], "source": "test"},
            body,
            commit_msg="test",
        )
        cv_env.idx.reindex_doc(p, body)
    bind_cid = cv_env.conv.create(role_id="default")
    first = cv_env.tools.search(
        {"query": token, "k": 3, "paths": ["lore://kb/"]},
        conversation_id=bind_cid,
    )
    assert first.get("next_cursor"), first
    assert first.get("has_more") is True
    ids1 = {h.get("doc_id") for h in first.get("hits") or []}
    second = cv_env.tools.search(
        {
            "query": token,
            "k": 3,
            "cursor": first["next_cursor"],
            "paths": ["lore://kb/"],
        },
        conversation_id=bind_cid,
    )
    ids2 = {h.get("doc_id") for h in second.get("hits") or []}
    assert ids1.isdisjoint(ids2)
    other_cid = cv_env.conv.create(role_id="default")
    expired = cv_env.tools.search(
        {"query": token, "k": 3, "cursor": first["next_cursor"]},
        conversation_id=other_cid,
    )
    assert expired.get("cursor_expired") is True


def test_select_tools_api_includes_search_read_list():
    names = {d["function"]["name"] for d in select_tools(MODE_API, web_enabled=False)}
    assert {"search", "read", "list"}.issubset(names)


@pytest.mark.asyncio
async def test_tool_loop_api_mode_runs_search(tmp_path):
    kb = tmp_path / "knowledge"
    kb.mkdir()
    settings = Settings(kb_path=kb)
    llm = FakeLLMClient(
        tool_responses=[
            {
                "content": None,
                "tool_calls": [
                    ToolCall(id="1", name="search", arguments={"query": "hello"}),
                ],
            },
            {"content": "done", "tool_calls": []},
        ],
        embed_dim=8,
    )
    repo = KnowledgeRepo(kb)
    ci = make_conversation_index(tmp_path, llm)
    retr = Retriever(ci.search_index, llm)
    pending = PendingStore(kb / ".kb" / "pending.json")
    writer = make_writer(repo, tmp_path)
    org = Organizer(
        repo=repo,
        retriever=retr,
        pending=pending,
        llm=llm,
        knowledge_writer=writer,
    )
    registry = ToolRegistry(
        retr,
        repo,
        org,
        WebFetcher(5, 1000),
        WebSearch(settings, cooldown=CooldownStore(settings.kb_path / ".kb" / "search_cd.json")),
        pending,
        writer,
        conversations=ConversationStore(kb / ".kb" / "conversations"),
    )
    loop = AgentToolLoop(settings, llm, registry)
    tools_for_run = select_tools(MODE_API, web_enabled=False)
    names = {t["function"]["name"] for t in tools_for_run}
    assert "search" in names
    cid = registry.conversations.create(role_id="default")
    loop._tool_progress = ToolProgressExecutor(registry.execute)
    events: list[str] = []
    async for ev in loop.stream(
        [{"role": "user", "content": "q"}],
        tools_for_run=tools_for_run,
        conversation_id=cid,
        active_doc_path=None,
    ):
        events.append(ev)
    assert any("event: tool_result" in e and "search" in e for e in events)
