import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models.llm import FakeLLMClient


@pytest.fixture
def demo_client(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge", demo_mode=True)
    llm = FakeLLMClient(chat_responses=["ok"] * 20, embed_dim=8)
    app = create_app(settings=settings, llm=llm)
    with TestClient(app) as client:
        yield client


def test_status_reports_demo_and_role(demo_client):
    body = demo_client.get("/api/auth/status").json()
    assert body["demo"] is True
    assert body["role"] in ("none", "guest")


def test_guest_endpoint_issues_cookie(demo_client):
    r = demo_client.post("/api/auth/guest")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "role": "guest"}
    assert "lorechat_guest" in r.cookies


def test_guest_cookie_grants_read_access(demo_client):
    demo_client.post("/api/auth/guest")
    r = demo_client.get("/api/tree")
    assert r.status_code == 200


def test_status_role_is_guest_after_issue(demo_client):
    demo_client.post("/api/auth/guest")
    assert demo_client.get("/api/auth/status").json()["role"] == "guest"


def test_setup_is_forbidden_in_demo(demo_client):
    """否则任何访客都能抢先把自己设成管理员。"""
    r = demo_client.post("/api/auth/setup", json={"password": "hijack-me-12345"})
    assert r.status_code == 403
    assert r.json()["code"] == "demo_setup_disabled"


def test_guest_endpoint_absent_outside_demo(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge")
    llm = FakeLLMClient(chat_responses=["ok"] * 20, embed_dim=8)
    app = create_app(settings=settings, llm=llm)
    with TestClient(app) as client:
        assert client.post("/api/auth/guest").status_code == 403


def test_guest_sessions_do_not_touch_sessions_json(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge", demo_mode=True)
    llm = FakeLLMClient(chat_responses=["ok"] * 20, embed_dim=8)
    app = create_app(settings=settings, llm=llm)
    with TestClient(app) as client:
        client.post("/api/auth/guest")
        client.get("/api/tree")
    assert not (tmp_path / "knowledge" / ".kb" / "sessions.json").exists()
