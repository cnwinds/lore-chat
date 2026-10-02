"""ContextViewTools.read"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.engine.agent.tools import ToolRegistry
from app.engine.conversations import ConversationStore
from app.engine.organizer import Organizer
from app.engine.pending import PendingStore
from app.engine.retriever import Retriever
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import WebSearch
from app.config import Settings
from app.models.cooldown import CooldownStore
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_conversation_index, make_writer
from tests.test_context_view_tools_common import cv_env  # noqa: F401


def _write_doc(env, path: str, body: str, *, title: str = "T"):
    meta = {"title": title, "tags": [], "source": "test"}
    env.repo.write_doc(path, meta, body, commit_msg="test")
    env.idx.reindex_doc(path, body)


def test_read_doc_meta_no_header_in_body(cv_env):
    _write_doc(cv_env, "读/元数据.md", "# 正文\n\nhello", title="Shown")
    cid = cv_env.conv.create(role_id="default")
    out = cv_env.tools.read({"uri": "读/元数据.md"}, conversation_id=cid)
    assert out.get("meta", {}).get("title") == "Shown"
    assert "<<<LORE_META" not in (out.get("body") or "")
    assert cv_env.tools.read_guard.is_read(cid, "读/元数据.md")


def test_read_text_file(cv_env):
    cv_env.repo.write_bytes("scripts/run.sh", b"echo hi\n", commit_msg="t")
    out = cv_env.tools.read({"uri": "scripts/run.sh"})
    assert out.get("kind") == "text"
    assert "echo hi" in (out.get("body") or "")


def test_read_binary_png_no_body(cv_env):
    cv_env.repo.write_bytes("img/x.png", b"\x89PNG\r\n", commit_msg="t")
    out = cv_env.tools.read({"uri": "img/x.png"})
    assert out.get("kind") == "binary"
    assert out.get("size") == 6
    assert "body" not in out or not out.get("body")


def test_read_binary_pdf_extracted(cv_env):
    cv_env.repo.write_bytes("doc/f.pdf", b"%PDF-1.4 fake", commit_msg="t")
    with patch(
        "app.engine.agent.tool_impl.context_view_tools.extract_text",
        return_value="抽取的正文",
    ):
        out = cv_env.tools.read({"uri": "doc/f.pdf"})
    assert out.get("extracted") is True
    assert "抽取的正文" in (out.get("body") or "")


def test_read_directory_error(cv_env):
    out = cv_env.tools.read({"uri": "lore://kb/"})
    assert out.get("error") == "is_directory"


def test_read_conversation_tail_and_anchored(cv_env):
    cid = cv_env.conv.create(role_id="default")
    turn = cv_env.conv.begin_turn(cid, user_text="第一条", client_message_id="u1")
    mid = turn["user_message"]["id"]
    cv_env.conv.finalize_turn(
        cid,
        turn["turn_id"],
        assistant={"text": "回复", "timeline": [], "sources": [], "status": "complete"},
    )
    tail = cv_env.tools.read(
        {"uri": f"lore://conversations/dm/default/{cid}/"},
        conversation_id=cid,
    )
    assert tail.get("messages")
    assert tail["messages"][0].get("uri")
    anchored = cv_env.tools.read(
        {
            "uri": f"lore://conversations/dm/default/{cid}/{mid}",
            "before": 0,
            "after": 0,
        },
        conversation_id=cid,
    )
    assert anchored.get("messages")


@pytest.mark.asyncio
async def test_read_then_edit_doc_uses_shared_read_guard(cv_env, tmp_path):
    path = "编辑/共享.md"
    _write_doc(cv_env, path, "# 正文\n\neditable", title="共享")
    cid = cv_env.conv.create(role_id="default")
    read_out = cv_env.tools.read({"uri": path}, conversation_id=cid)
    assert read_out.get("body")
    kb = tmp_path / "knowledge"
    settings = Settings(kb_path=kb)
    llm = FakeLLMClient(embed_dim=8)
    repo = cv_env.repo
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
    guard = cv_env.tools.read_guard
    registry = ToolRegistry(
        retr,
        repo,
        org,
        WebFetcher(5, 1000),
        WebSearch(settings, cooldown=CooldownStore(kb / ".kb" / "search_cd.json")),
        pending,
        writer,
        conversations=cv_env.conv,
        edit_doc_require_read=True,
    )
    registry.kb_mutate.read_guard = guard
    registry.context_view.read_guard = guard
    fail = await registry.execute(
        "edit_doc",
        {
            "path": "未读.md",
            "edits": [{"old_string": "x", "new_string": "y"}],
        },
        conversation_id=cid,
    )
    assert fail.get("error") == "NOT_READ"
    ok = await registry.execute(
        "edit_doc",
        {
            "path": path,
            "edits": [{"old_string": "editable", "new_string": "edited"}],
        },
        conversation_id=cid,
    )
    assert ok.get("error") != "NOT_READ"


def test_read_memory_include_sources_owner_vs_channel(cv_env):
    remember = cv_env.owner.remember("私密偏好条目", origin="explicit_remember")
    fid = remember["fact"]["id"]
    fact = cv_env.owner.store.get_fact(fid)
    kind = fact.get("category") or "preference"
    cv_env.owner.store.set_status(fid, "confirmed")
    cv_env.owner.store.add_evidence(
        fact_id=fid,
        conversation_id=cv_env.conv.create(role_id="default"),
        message_id="m1",
        start_char=0,
        end_char=2,
        quote_hash="00",
    )
    uri = f"lore://memory/owner/{kind}/{fid}"
    owner_cid = cv_env.conv.create(role_id="default")
    out_owner = cv_env.tools.read(
        {"uri": uri, "include_sources": True},
        conversation_id=owner_cid,
    )
    assert out_owner.get("statement")
    role = cv_env.roles.create(name="通道用", system_prompt="")
    persona = cv_env.roles.create_persona(name="P", system_prompt="")
    inst = cv_env.channel_instances.create(
        type_id="script_api",
        name="ch",
        persona_id=persona["id"],
        role_id=role["id"],
    )
    cv_env.channel_instances.update(inst["id"], include_owner_memory=True)
    ch_cid = cv_env.conv.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    out_ch = cv_env.tools.read(
        {"uri": uri, "include_sources": True},
        conversation_id=ch_cid,
    )
    assert not out_ch.get("sources")
