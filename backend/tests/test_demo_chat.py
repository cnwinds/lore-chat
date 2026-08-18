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


def test_guest_hits_session_quota(demo_app, guest):
    demo_app.state.demo_quota._per_session = 1
    assert guest.post("/api/chat", json={"text": "一"}).status_code == 200
    r = guest.post("/api/chat", json={"text": "二"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "demo_quota_exceeded"


def test_guest_input_length_is_capped(guest):
    r = guest.post("/api/chat", json={"text": "长" * 2001})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "demo_input_too_long"


def test_demo_lowers_tool_call_budget(tmp_path):
    from app.config import Settings
    from app.demo.quota import GUEST_MAX_TOOL_CALLS
    from app.engine.agent.tool_loop import resolve_max_tool_calls

    settings = Settings(kb_path=tmp_path / "kb", demo_mode=True, agent_max_tool_calls=25)
    assert resolve_max_tool_calls(settings) <= GUEST_MAX_TOOL_CALLS
