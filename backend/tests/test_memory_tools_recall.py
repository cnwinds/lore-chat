import pytest

from app.deps import build_container
from app.config import Settings


@pytest.fixture
def container(tmp_path):
    kb = tmp_path / "knowledge"
    kb.mkdir()
    return build_container(Settings(kb_path=kb))


@pytest.mark.asyncio
async def test_recall_returns_confirmed(container):
    await container.agent.tools.execute(
        "manage_memory",
        {"action": "remember", "statement": "记住我用 neovim"},
    )
    out = await container.agent.tools.execute(
        "recall_memory",
        {"query": "neovim", "limit": 5},
    )
    assert out["count"] == 1
    assert "neovim" in out["facts"][0]["statement"].lower()


@pytest.mark.asyncio
async def test_recall_sources_with_evidence(container):
    from app.engine.conversations import ConversationStore

    store = container.conversations
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="我喜欢简洁回答", client_message_id="c1", observation_allowed=False
    )
    mid = turn["user_message"]["id"]
    store.finalize_turn(
        cid,
        turn["turn_id"],
        assistant={"text": "好的", "timeline": [], "sources": [], "status": "complete"},
    )
    remember = container.memory_service.remember(
        "我喜欢简洁回答",
        conversation_id=cid,
        message_id=mid,
        start_char=0,
        end_char=7,
    )
    assert remember["ok"]
    out = container.memory_service.recall("简洁", include_sources=True, limit=5)
    assert out["facts"]
    sources = out["facts"][0].get("sources") or []
    # 出处以会话为准（session:…）；字级 message_id 仅为兼容旧调用方
    assert sources
    assert any(s.get("conversation_id") == cid for s in sources)
    assert any(
        s.get("message_id") == mid or str(s.get("message_id") or "").startswith("session:")
        for s in sources
    )
