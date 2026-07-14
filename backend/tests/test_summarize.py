import json

import pytest

from app.config import Settings
from app.engine.agent.system_layer import SystemLayer
from app.engine.agent.tools import ToolRegistry
from app.engine.conversations import ConversationStore
from app.engine.derivation_worker import DerivationWorker
from app.engine.organizer import Organizer
from app.engine.pending import PendingStore
from app.engine.retriever import Retriever
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import WebSearch
from app.index.conversation_fts import ConversationFTS
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo


def _decision(rel_path="娱乐/漫剧工具盘点.md"):
    return json.dumps(
        {
            "action": "new",
            "rel_path": rel_path,
            "title": "漫剧工具盘点",
            "category": "娱乐",
            "tags": ["漫剧"],
            "ambiguous": False,
            "reason": "会话归档",
        }
    )


def _make(tmp_path, chat_responses):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(chat_responses=chat_responses, embed_dim=8)
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm, excluded_prefixes=("系统/",))
    pending = PendingStore(tmp_path / "knowledge" / ".kb" / "pending.json")
    org = Organizer(repo=repo, retriever=retr, indexer=idx, pending=pending, llm=llm)
    conversations = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    conversation_fts = ConversationFTS(tmp_path / "knowledge" / ".kb" / "index" / "conversation_fts.db")
    derivation_worker = DerivationWorker(conversations, conversation_fts)
    system_layer = SystemLayer(repo)
    settings = Settings(kb_path=tmp_path / "knowledge")
    registry = ToolRegistry(
        retr,
        repo,
        org,
        WebFetcher(),
        WebSearch(settings),
        pending,
        conversations=conversations,
        system_layer=system_layer,
        indexer=idx,
    )
    return registry, repo, conversations, idx, conversation_fts, derivation_worker


def test_conversation_tracks_summary_state(tmp_path):
    store = ConversationStore(tmp_path / "conv")
    cid = store.create()
    conv = store.get(cid)
    assert conv["summarized"] is False
    assert conv["summary_path"] is None

    store.append_exchange(cid, "问漫剧工具", {"role": "assistant", "text": "回答"})
    assert store.get(cid)["indexed_dirty"] is True

    store.mark_summarized(cid, "娱乐/漫剧工具盘点.md")
    conv = store.get(cid)
    assert conv["summarized"] is True
    assert conv["summary_path"] == "娱乐/漫剧工具盘点.md"
    assert conv["indexed_dirty"] is False

    # 归档后又追加 → 重新可检索（脏）
    store.append_exchange(cid, "补充问题", {"role": "assistant", "text": "补充"})
    conv = store.get(cid)
    assert conv["summarized"] is False
    assert conv["indexed_dirty"] is True


def test_full_transcript_includes_both_roles(tmp_path):
    store = ConversationStore(tmp_path / "conv")
    cid = store.create()
    store.append_exchange(cid, "有哪些漫剧工具", {"role": "assistant", "text": "剪映、小云雀"})
    transcript = ConversationStore.full_transcript(store.get(cid))
    assert "【用户】有哪些漫剧工具" in transcript
    assert "【助手】剪映、小云雀" in transcript


@pytest.mark.asyncio
async def test_summarize_conversation_tool_flow(tmp_path, monkeypatch):
    # chat 顺序：_synthesize 正文 → _understand 摘要 → _decide 决策
    synthesized = "# 漫剧工具盘点\n\n剪映、小云雀等工具的综合介绍。\n"
    registry, repo, conversations, idx, conversation_fts, derivation_worker = _make(
        tmp_path, [synthesized, "漫剧工具", _decision()]
    )
    cid = conversations.create()
    turn = conversations.begin_turn(
        cid, user_text="有哪些漫剧工具", client_message_id="cli-1", observation_allowed=False
    )
    conversations.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={"text": "剪映、小云雀", "timeline": [], "sources": [], "status": "complete"},
    )
    derivation_worker.drain(max_jobs=10)
    assert conversation_fts.query("小云雀", k=5), "消息应已进入会话全文索引"

    removed: list[str] = []
    monkeypatch.setattr(idx, "remove_conversation", lambda cid: removed.append(cid))

    result = await registry.execute(
        "summarize_conversation", {}, conversation_id=cid
    )
    assert "已归档" in result["summary"]
    assert result["sources"][0]["path"] == "娱乐/漫剧工具盘点.md"

    # 会话被标记已总结
    conv = conversations.get(cid)
    assert conv["summarized"] is True
    assert conv["summary_path"] == "娱乐/漫剧工具盘点.md"
    doc = repo.read_doc("娱乐/漫剧工具盘点.md")
    assert "漫剧工具盘点" in doc.body
    assert doc.meta.get("conversation_ids") == [cid]
    assert doc.meta.get("source") == "conversation"

    # 归档不应清空原会话消息的全文索引，也不应调用 remove_conversation
    assert removed == []
    hits = conversation_fts.query("小云雀", k=5)
    assert any(h.conversation_id == cid for h in hits)


@pytest.mark.asyncio
async def test_summarize_without_conversation_context(tmp_path):
    registry, *_ = _make(tmp_path, [])
    result = await registry.execute("summarize_conversation", {}, conversation_id=None)
    assert result.get("error")


def test_summarize_endpoint_keeps_message_fts_and_skips_remove_conversation(
    tmp_path, monkeypatch
):
    """覆盖 routes.py 的 /conversations/{cid}/summarize 端点（独立于 tools.py 的调用点）。"""
    from fastapi.testclient import TestClient

    from app.main import create_app

    synthesized = "# 漫剧工具盘点\n\n剪映、小云雀等工具的综合介绍。\n"
    llm = FakeLLMClient(
        chat_responses=[synthesized, "漫剧工具", _decision()], embed_dim=8
    )
    settings = Settings(kb_path=tmp_path / "knowledge")
    app = create_app(settings=settings, llm=llm)

    with TestClient(app) as client:
        c = app.state.container
        cid = c.conversations.create()
        turn = c.conversations.begin_turn(
            cid,
            user_text="有哪些漫剧工具",
            client_message_id="cli-1",
            observation_allowed=False,
        )
        c.conversations.finalize_turn(
            cid,
            turn_id=turn["turn_id"],
            assistant={
                "text": "剪映、小云雀",
                "timeline": [],
                "sources": [],
                "status": "complete",
            },
        )
        c.derivation_worker.drain(max_jobs=10)
        assert c.conversation_fts.query("小云雀", k=5), "消息应已进入会话全文索引"

        removed: list[str] = []
        monkeypatch.setattr(
            c.indexer, "remove_conversation", lambda cid: removed.append(cid)
        )

        r = client.post(f"/api/conversations/{cid}/summarize")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "saved"

        conv = c.conversations.get(cid)
        assert conv["summarized"] is True
        assert conv["summary_path"] == "娱乐/漫剧工具盘点.md"

        assert removed == []
        hits = c.conversation_fts.query("小云雀", k=5)
        assert any(h.conversation_id == cid for h in hits)
