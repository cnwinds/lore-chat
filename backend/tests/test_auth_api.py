from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models.llm import FakeLLMClient


def _raw_client(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge")
    app = create_app(settings=settings, llm=FakeLLMClient(embed_dim=8))
    return TestClient(app)


def test_health_public(tmp_path):
    with _raw_client(tmp_path) as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["capabilities"]["sandbox"] is False


def test_health_sandbox_capability_when_enabled(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge", sandbox_enabled=True)
    app = create_app(settings=settings, llm=FakeLLMClient(embed_dim=8))
    with TestClient(app) as c:
        body = c.get("/api/health").json()
        assert body["capabilities"]["sandbox"] is True


def test_tree_requires_auth(tmp_path):
    with _raw_client(tmp_path) as c:
        r = c.get("/api/tree")
        assert r.status_code == 401
        assert r.json()["code"] == "auth_required"


def test_setup_login_logout_flow(tmp_path):
    with _raw_client(tmp_path) as c:
        st = c.get("/api/auth/status").json()
        assert st["setup_required"] is True
        assert st["authenticated"] is False

        r = c.post("/api/auth/setup", json={"password": "admin-pass-123"})
        assert r.status_code == 200
        assert c.cookies.get("lorechat_session")

        st2 = c.get("/api/auth/status").json()
        assert st2["setup_required"] is False
        assert st2["authenticated"] is True

        assert c.get("/api/tree").status_code == 200

        r2 = c.post("/api/auth/setup", json={"password": "another-pass"})
        assert r2.status_code == 403

        c.post("/api/auth/logout")
        assert c.get("/api/tree").status_code == 401

        bad = c.post("/api/auth/login", json={"password": "wrong-password"})
        assert bad.status_code == 401

        ok = c.post("/api/auth/login", json={"password": "admin-pass-123"})
        assert ok.status_code == 200
        assert c.get("/api/tree").status_code == 200


def test_change_password_flow(tmp_path):
    with _raw_client(tmp_path) as c:
        c.post("/api/auth/setup", json={"password": "admin-pass-123"})

        bad = c.post(
            "/api/auth/change-password",
            json={"old_password": "wrong", "new_password": "new-pass-456"},
        )
        assert bad.status_code == 401

        ok = c.post(
            "/api/auth/change-password",
            json={"old_password": "admin-pass-123", "new_password": "new-pass-456"},
        )
        assert ok.status_code == 200

        c.post("/api/auth/logout")

        old_login = c.post("/api/auth/login", json={"password": "admin-pass-123"})
        assert old_login.status_code == 401

        new_login = c.post("/api/auth/login", json={"password": "new-pass-456"})
        assert new_login.status_code == 200
