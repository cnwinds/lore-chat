import logging

import pytest

from app.engine.agent.run_report import AgentRunReport


def test_run_report_emit_formats_key_fields(caplog):
    caplog.set_level(logging.INFO, logger="lorechat.agent.tool_loop")
    logger = logging.getLogger("lorechat.agent.tool_loop")
    AgentRunReport(
        layer="agent",
        stop_reason="assistant_reply",
        conversation_id="abc123",
        turn_id="turn-1",
        run_id="run-1",
        llm_rounds=2,
        tool_calls_total=1,
        tool_limit=20,
        last_tool_names=["search_kb"],
        done_emitted=True,
        duration_ms=1500,
    ).emit(logger)

    assert len(caplog.records) == 1
    msg = caplog.records[0].message
    assert "agent run end" in msg
    assert "stop_reason=assistant_reply" in msg
    assert "cid=abc123" in msg
    assert "turn_id=turn-1" in msg
    assert "run_id=run-1" in msg
    assert "last_tools=search_kb" in msg
    assert "done_emitted=True" in msg


@pytest.mark.asyncio
async def test_tool_loop_logs_complete_stop_reason(tmp_path, caplog):
    from app.config import Settings
    from app.engine.agent.tool_loop import AgentToolLoop
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

    caplog.set_level(logging.INFO)
    kb = tmp_path / "knowledge"
    settings = Settings(kb_path=kb)
    llm = FakeLLMClient(
        tool_responses=[
            {
                "content": None,
                "tool_calls": [
                    ToolCall(id="1", name="search_kb", arguments={"query": "x"}),
                ],
            },
            {"content": "结论", "tool_calls": []},
        ],
        embed_dim=8,
    )
    repo = KnowledgeRepo(kb)
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm)
    pending = PendingStore(kb / ".kb" / "pending.json")
    org = Organizer(repo=repo, retriever=retr, indexer=idx, pending=pending, llm=llm)
    registry = ToolRegistry(
        retr, repo, org, WebFetcher(5, 1000), WebSearch(settings), pending
    )
    loop = AgentToolLoop(settings, llm, registry)

    async for _ in loop.stream(
        [{"role": "user", "content": "q"}],
        tools_for_run=[],
        conversation_id="cid1",
        active_doc_path=None,
        turn_id="t1",
        run_id="r1",
    ):
        pass

    end_logs = [r.message for r in caplog.records if "agent run end" in r.message]
    assert end_logs
    assert "stop_reason=assistant_reply" in end_logs[-1]
    assert "tool_calls=1" in end_logs[-1]
    assert "llm_rounds=2" in end_logs[-1]


@pytest.mark.asyncio
async def test_tool_loop_logs_cancelled_stop_reason(tmp_path, caplog):
    from app.config import Settings
    from app.engine.agent.tool_loop import AgentToolLoop
    from app.engine.agent.tools import ToolRegistry
    from app.engine.organizer import Organizer
    from app.engine.pending import PendingStore
    from app.engine.retriever import Retriever
    from app.engine.web.search import WebSearch
    from app.index.fulltext import FullTextIndex
    from app.index.indexer import Indexer
    from app.index.vector import VectorIndex
    from app.models.llm import ChatStreamChunk, ChatWithToolsResult, FakeLLMClient
    from app.storage.repo import KnowledgeRepo

    caplog.set_level(logging.WARNING)
    kb = tmp_path / "knowledge"
    settings = Settings(kb_path=kb)
    llm = FakeLLMClient(tool_responses=[], embed_dim=8)

    class HangThenCancelLLM(FakeLLMClient):
        def stream_chat_with_tools(self, messages, tools, *, big=True, temperature=0.2):
            yield ChatStreamChunk(text_delta="partial")
            yield ChatStreamChunk(
                result=ChatWithToolsResult(content="partial", tool_calls=[])
            )

    llm = HangThenCancelLLM(tool_responses=[], embed_dim=8)
    repo = KnowledgeRepo(kb)
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm)
    pending = PendingStore(kb / ".kb" / "pending.json")
    org = Organizer(repo=repo, retriever=retr, indexer=idx, pending=pending, llm=llm)
    registry = ToolRegistry(retr, repo, org, None, WebSearch(settings), pending)
    loop = AgentToolLoop(settings, llm, registry)

    gen = loop.stream(
        [{"role": "user", "content": "q"}],
        tools_for_run=[],
        conversation_id="cid1",
        active_doc_path=None,
        run_id="r-cancel",
    )
    await gen.__anext__()
    await gen.aclose()

    end_logs = [r.message for r in caplog.records if "agent run end" in r.message]
    assert end_logs
    assert "stop_reason=consumer_aborted" in end_logs[-1] or "stop_reason=cancelled" in end_logs[
        -1
    ]
