import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models.llm import FakeLLMClient


@pytest.fixture
def demo_app(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge", demo_mode=True)
    llm = FakeLLMClient(chat_responses=["演示回答"] * 40, embed_dim=8)
    return create_app(settings=settings, llm=llm)


@pytest.fixture
def seeded_cid(demo_app):
    with TestClient(demo_app) as admin:
        sid = demo_app.state.session_store.create()
        admin.cookies.set("lorechat_session", sid)
        cid = admin.post("/api/conversations", json={"title": "选型"}).json()["id"]
        admin.post(
            f"/api/conversations/{cid}/messages",
            json={"role": "user", "text": "向量库怎么选"},
        )
        return cid


def test_ephemeral_from_streams(demo_app, seeded_cid):
    with TestClient(demo_app) as guest:
        guest.post("/api/auth/guest")
        r = guest.post("/api/chat", json={"text": "为什么", "ephemeral_from": seeded_cid})
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")


def test_ephemeral_from_does_not_grow_source_conversation(demo_app, seeded_cid):
    with TestClient(demo_app) as guest:
        guest.post("/api/auth/guest")
        before = len(guest.get(f"/api/conversations/{seeded_cid}").json()["messages"])
        guest.post("/api/chat", json={"text": "为什么", "ephemeral_from": seeded_cid})
        after = len(guest.get(f"/api/conversations/{seeded_cid}").json()["messages"])
        assert after == before


def test_ephemeral_from_unknown_conversation_is_404(demo_app):
    with TestClient(demo_app) as guest:
        guest.post("/api/auth/guest")
        r = guest.post("/api/chat", json={"text": "hi", "ephemeral_from": "missing"})
        assert r.status_code == 404
