"""read_last_tool_results：上一轮工具/检索原文按需取回（不再每轮注入）。"""

from app.engine.agent.tool_impl.kb_read import KbReadTools
from app.engine.conversations import ConversationStore
from app.engine.disclosure import DisclosureWindows


def _tool(conversations):
    return KbReadTools(
        repo=None,
        retriever=None,
        read_guard=None,
        disclosure_windows=DisclosureWindows(),
        conversations=conversations,
    )


def _save_turn_with_tools(store, cid, user_text, tools_blocks, reply, n=[0]):
    n[0] += 1
    turn = store.begin_turn(
        cid, user_text=user_text, client_message_id=f"cm-{n[0]}"
    )
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={
            "text": reply,
            "timeline": tools_blocks,
            "sources": [],
            "status": "complete",
        },
    )


def test_returns_last_turn_tool_blocks(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    _save_turn_with_tools(
        store,
        cid,
        "查一下 RRF",
        [
            {"type": "tool", "tool": "web_search", "label": "搜索网页",
             "query": "RRF k=60", "content": "命中 1：RRF 原始论文……" * 3},
            {"type": "tool", "tool": "search_kb", "label": "检索知识库",
             "query": "RRF 检索", "summary": "本地未命中"},
        ],
        "RRF 是一种倒数排序融合方法。",
    )
    tool = _tool(store)
    out = tool.read_last_tool_results({}, conversation_id=cid)
    assert out["results"][0]["tool"] == "web_search"
    assert "RRF 原始论文" in out["results"][0]["content"]
    assert out["results"][1]["content"] == "本地未命中"
    assert out["truncated"] is False


def test_empty_when_no_tool_calls(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    _save_turn_with_tools(store, cid, "在吗", [], "在的。")
    out = _tool(store).read_last_tool_results({}, conversation_id=cid)
    assert out["results"] == []
    assert "没有工具" in out["summary"]


def test_long_content_is_clipped(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    _save_turn_with_tools(
        store,
        cid,
        "抓这个页面",
        [
            {"type": "tool", "tool": "fetch_url", "label": "读取链接",
             "query": "https://example.com", "content": "长" * 9000},
        ],
        "页面要点是……",
    )
    out = _tool(store).read_last_tool_results({}, conversation_id=cid)
    assert out["truncated"] is True
    assert len(out["results"][0]["content"]) <= 2410


def test_missing_conversation(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    out = _tool(store).read_last_tool_results({}, conversation_id="nope")
    assert out["error"] == "not_found"
