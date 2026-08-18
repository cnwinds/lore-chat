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
def guest(demo_app):
    with TestClient(demo_app) as client:
        client.post("/api/auth/guest")
        yield client


def test_guest_ephemeral_chat_streams(guest):
    r = guest.post("/api/chat", json={"text": "Lore 是什么"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")


def test_guest_chat_with_conversation_id_is_rejected(guest):
    r = guest.post("/api/chat", json={"text": "hi", "conversation_id": "any"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "demo_read_only"


def test_guest_chat_creates_no_conversation(demo_app, guest):
    guest.post("/api/chat", json={"text": "Lore 是什么"})
    assert guest.get("/api/conversations").json()["conversations"] == []
