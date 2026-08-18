import pytest
from fastapi.testclient import TestClient
from starlette.routing import Route

from app.config import Settings
from app.demo.guard import GUEST_READ_ROUTES
from app.main import create_app
from app.models.llm import FakeLLMClient


@pytest.fixture
def demo_app(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge", demo_mode=True)
    llm = FakeLLMClient(chat_responses=["ok"] * 40, embed_dim=8)
    return create_app(settings=settings, llm=llm)


@pytest.fixture
def guest(demo_app):
    with TestClient(demo_app) as client:
        client.post("/api/auth/guest")
        yield client


def _api_routes(app) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, Route) or not route.path.startswith("/api/"):
            continue
        for method in sorted(route.methods or set()):
            if method in ("HEAD", "OPTIONS"):
                continue
            out.append((method, route.path))
    return out


def test_whitelist_only_names_real_routes(demo_app):
    """白名单里写错路径会静默失效，必须钉死。"""
    known = set(_api_routes(demo_app))
    unknown = {r for r in GUEST_READ_ROUTES if r not in known}
    assert unknown == set()


def test_every_non_whitelisted_route_is_forbidden_for_guest(demo_app, guest):
    """新增路由默认对访客关闭。这条失败说明有接口意外向公网开放了。"""
    opened: list[tuple[str, str]] = []
    for method, template in _api_routes(demo_app):
        if (method, template) in GUEST_READ_ROUTES:
            continue
        url = template.replace("{cid}", "x").replace("{merge_id}", "x")
        url = url.replace("{qid}", "x").replace("{fact_id}", "x")
        url = url.replace("{path:path}", "x")
        r = guest.request(method, url)
        if r.status_code != 403 or r.json().get("code") != "demo_read_only":
            opened.append((method, template))
    assert opened == []


def test_export_is_blocked_for_guest(guest):
    """导出包含 auth.json 与明文密钥的 settings.json。"""
    r = guest.get("/api/admin/export")
    assert r.status_code == 403
    assert r.json()["code"] == "demo_read_only"


def test_download_zip_is_blocked_for_guest(guest):
    r = guest.get("/api/download-zip")
    assert r.status_code == 403


def test_whitelisted_read_passes(guest):
    assert guest.get("/api/tree").status_code == 200
    assert guest.get("/api/conversations").status_code == 200
    assert guest.get("/api/memory/facts").status_code == 200


def test_admin_is_not_restricted(demo_app):
    """demo 站的管理员走密码登录，行为与非 demo 部署一致。"""
    with TestClient(demo_app) as client:
        sid = demo_app.state.session_store.create()
        client.cookies.set("lorechat_session", sid)
        r = client.put("/api/doc", json={"path": "技术/x.md", "text": "hi"})
        assert r.status_code != 403
