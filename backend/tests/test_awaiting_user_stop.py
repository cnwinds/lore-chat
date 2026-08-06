"""ask_user / sandbox_confirm 应结束本轮，等待用户。"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.engine.agent.tool_loop import AgentToolLoop, tool_awaits_user
from app.engine.agent.tools import ToolRegistry
from app.engine.organizer import Organizer
from app.engine.pending import PendingStore
from app.engine.retriever import Retriever
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import WebSearch
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient, ToolCall
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


def test_tool_awaits_user_detects_confirm_shapes():
    assert tool_awaits_user({"awaiting_user": True}) is True
    assert tool_awaits_user({"awaiting_confirm": True}) is True
    assert tool_awaits_user(
        {"question_id": "q1", "options": [{"id": "a", "label": "A"}]}
    ) is True
    assert tool_awaits_user({"question_id": "q1", "options": []}) is False
    assert tool_awaits_user({"summary": "ok"}) is False


def _build_loop(tmp_path, llm: FakeLLMClient) -> AgentToolLoop:
    kb = tmp_path / "knowledge"
    settings = Settings(kb_path=kb)
    repo = KnowledgeRepo(kb)
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm)
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
        WebSearch(settings),
        pending,
        writer,
    )
    return AgentToolLoop(settings, llm, registry)


@pytest.mark.asyncio
async def test_ask_user_stops_loop_without_extra_llm_round(tmp_path, caplog):
    import logging

    caplog.set_level(logging.INFO)
    llm = FakeLLMClient(
        tool_responses=[
            {
                "content": None,
                "tool_calls": [
                    ToolCall(
                        id="1",
                        name="ask_user",
                        arguments={
                            "question": "选哪个？",
                            "options": [
                                {"id": "a", "label": "A"},
                                {"id": "b", "label": "B"},
                            ],
                        },
                    ),
                ],
            },
            # 若未停下，会吃到第二轮并继续；断言 stop_reason 即可
            {"content": "不该走到这里", "tool_calls": []},
        ],
        embed_dim=8,
    )
    loop = _build_loop(tmp_path, llm)
    events: list[str] = []
    async for ev in loop.stream(
        [{"role": "user", "content": "q"}],
        tools_for_run=[],
        conversation_id="cid",
        active_doc_path=None,
        turn_id="t1",
        run_id="r1",
    ):
        events.append(ev)

    assert any("event: done" in e for e in events)
    assert any("等待用户选择" in e or "question_id" in e for e in events)
    end_logs = [r.message for r in caplog.records if "agent run end" in r.message]
    assert end_logs
    assert "stop_reason=awaiting_user" in end_logs[-1]
    # ask_user 后不应再向 LLM 要第二轮
    assert llm._i == 1
