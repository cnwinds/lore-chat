"""会话上下文统计接口：容量、分段、缓存命中率。"""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models.llm import FakeLLMClient


@pytest.fixture
def client(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge")
    llm = FakeLLMClient(chat_responses=["回答"] * 20, embed_dim=8)
    app = create_app(settings=settings, llm=llm)
    with TestClient(app) as c:
        sid = app.state.session_store.create()
        c.cookies.set("lorechat_session", sid)
        yield c


def test_context_stats_shape(client):
    cid = client.post("/api/conversations", json={"title": "统计"}).json()["id"]
    client.post(
        f"/api/conversations/{cid}/messages",
        json={"messages": [{"role": "user", "text": "你好"}]},
    )
    r = client.get(f"/api/conversations/{cid}/context-stats")
    assert r.status_code == 200
    body = r.json()
    keys = [seg["key"] for seg in body["segments"]]
    assert keys == [
        "system",
        "memory",
        "skill",
        "history",
        "tools",
        "attachments",
    ]
    memory = next(s for s in body["segments"] if s["key"] == "memory")
    assert "preview" in memory
    assert isinstance(memory["tokens"], int)
    assert body["tool_calls"] == 0
    assert body["cache_hit_rate"] is None
    # FakeLLM 不产生真实用量事件 → used_tokens 允许为 None
    assert body["context"]["used_tokens"] is None or isinstance(
        body["context"]["used_tokens"], int
    )
    assert body["context"]["limit_tokens"] is None or isinstance(
        body["context"]["limit_tokens"], int
    )


def test_context_stats_unknown_conversation_is_404(client):
    r = client.get("/api/conversations/nope/context-stats")
    assert r.status_code == 404
