"""会话上下文统计接口。"""

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
    assert isinstance(body["segments"], list)
    assert "latest_call_id" in body
    assert "captured_at" in body
    assert body["tool_calls"] == 0
    assert body["cache_hit_rate"] is None


def test_context_stats_unknown_conversation_is_404(client):
    r = client.get("/api/conversations/nope/context-stats")
    assert r.status_code == 404


def test_requests_list_empty(client):
    cid = client.post("/api/conversations", json={"title": "r"}).json()["id"]
    r = client.get(f"/api/conversations/{cid}/requests")
    assert r.status_code == 200
    assert r.json()["calls"] == []
