"""聊天通道 P0：公共模型、Key 投影、实例列表。"""

import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.engine.api_keys import ApiKeyStore, hash_api_key, mint_api_key
from app.engine.channel_plugins.registry import ChannelPluginRegistry
from app.engine.channel_plugins.store import ChannelInstanceStore
from app.engine.channel_plugins.types import SCRIPT_API_TYPE_ID, is_channel_origin
from app.engine.roles import API_ROLE_PREFIX, EXT_ROLE_PREFIX, is_api_role_id
from app.main import create_app
from app.models.llm import FakeLLMClient


def _text_llm() -> FakeLLMClient:
    return FakeLLMClient(
        chat_responses=["ok"] * 20,
        tool_responses=[{"content": "通道已收到", "tool_calls": []}] * 20,
        embed_dim=8,
    )


def _setup(tmp_path, llm=None):
    settings = Settings(kb_path=tmp_path / "knowledge")
    app = create_app(settings=settings, llm=llm or _text_llm())
    client = TestClient(app)
    client.__enter__()
    r = client.post("/api/auth/setup", json={"password": "test-password-123"})
    assert r.status_code == 200, r.text
    return app, client


def _close(client: TestClient) -> None:
    client.__exit__(None, None, None)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_registry_lists_script_and_upcoming_types():
    types = {item["type_id"]: item for item in ChannelPluginRegistry.builtin().list_types()}
    assert types[SCRIPT_API_TYPE_ID]["available"] is True
    assert types[SCRIPT_API_TYPE_ID]["display_name"] == "脚本 / HTTP"
    assert types["feishu"]["available"] is True
    assert types["slack"]["available"] is True
    assert types["wecom"]["available"] is True
    assert types["dingtalk"]["available"] is True
    assert types["wechat_mp"]["available"] is False


def test_is_api_role_id_covers_ext_prefix():
    assert is_api_role_id(f"{API_ROLE_PREFIX}abc")
    assert is_api_role_id(f"{EXT_ROLE_PREFIX}xyz")
    assert not is_api_role_id("default")


def test_is_channel_origin_set():
    assert is_channel_origin("api")
    assert is_channel_origin("feishu")
    assert is_channel_origin("slack")
    assert is_channel_origin("wecom")
    assert is_channel_origin("dingtalk")
    assert not is_channel_origin("web")
    assert not is_channel_origin(None)


def test_store_projects_legacy_api_keys(tmp_path):
    kb = tmp_path / "kb"
    (kb / ".kb").mkdir(parents=True)
    raw = mint_api_key()
    kid = "legacykey01"
    payload = {
        "keys": [
            {
                "id": kid,
                "name": "旧脚本",
                "hash": hash_api_key(raw),
                "prefix": raw[:12],
                "persona_id": "p1",
                "role_id": f"{API_ROLE_PREFIX}{kid}",
                "revoked": False,
                "created_at": "2026-09-01T00:00:00+00:00",
                "last_used_at": None,
            }
        ]
    }
    (kb / ".kb" / "api_keys.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    keys = ApiKeyStore(kb)
    store = ChannelInstanceStore(kb, api_keys=keys)
    assert store.project_legacy_keys() == 1
    listed = store.list_all()
    assert len(listed) == 1
    inst = listed[0]
    assert inst["id"] == kid
    assert inst["type_id"] == SCRIPT_API_TYPE_ID
    assert inst["name"] == "旧脚本"
    assert inst["enabled"] is True
    assert inst["role_id"] == f"{API_ROLE_PREFIX}{kid}"
    assert "key_hash" not in json.dumps(inst)
    rec = store.resolve_script_token(raw)
    assert rec is not None
    assert rec["id"] == kid
    assert rec["revoked"] is False
    dumped = json.dumps(listed)
    assert raw not in dumped
    assert "key_plaintext" not in dumped
    assert "key_hash" not in dumped
    internal = store.get_internal(kid)
    assert "key_plaintext" not in (internal.get("secrets") or {})
    assert (internal.get("secrets") or {}).get("key_hash")
    assert inst["config"]["key_prefix"] == raw[:12]


def test_store_dual_writes_script_key(tmp_path):
    kb = tmp_path / "kb"
    store = ChannelInstanceStore(kb, api_keys=ApiKeyStore(kb))
    raw, inst = store.create_script(
        name="新脚本",
        persona_id="p1",
        role_id="api_new01",
        instance_id="new01",
    )
    assert raw.startswith("lc_live_")
    keys = json.loads((kb / ".kb" / "api_keys.json").read_text(encoding="utf-8"))
    assert keys["keys"][0]["id"] == "new01"
    assert keys["keys"][0]["hash"] == hash_api_key(raw)
    assert inst["config"]["key_prefix"] == raw[:12]
    dumped = json.dumps(inst)
    assert raw not in dumped
    assert "key_plaintext" not in dumped
    internal = store.get_internal("new01")
    assert internal["secrets"]["key_plaintext"] == raw


def test_list_instances_includes_projected_keys(tmp_path):
    kb = tmp_path / "knowledge"
    (kb / ".kb").mkdir(parents=True)
    raw = mint_api_key()
    kid = "projkey01"
    (kb / ".kb" / "api_keys.json").write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "id": kid,
                        "name": "投影密钥",
                        "hash": hash_api_key(raw),
                        "prefix": raw[:12],
                        "persona_id": None,
                        "role_id": f"{API_ROLE_PREFIX}{kid}",
                        "revoked": False,
                        "created_at": "2026-09-01T00:00:00+00:00",
                        "last_used_at": None,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app, client = _setup(tmp_path)
    try:
        listed = client.get("/api/channel-plugins/instances")
        assert listed.status_code == 200, listed.text
        items = listed.json()["instances"]
        assert any(item["id"] == kid and item["type_id"] == SCRIPT_API_TYPE_ID for item in items)
        keys = client.get("/api/open-api/keys")
        assert keys.status_code == 200
        assert any(item["id"] == kid for item in keys.json()["keys"])
        types = client.get("/api/channel-plugins/types").json()["types"]
        assert any(item["type_id"] == SCRIPT_API_TYPE_ID and item["available"] for item in types)
        assert any(item["type_id"] == "feishu" and item["available"] for item in types)
    finally:
        _close(client)


def test_v1_chat_still_works_after_projection(tmp_path):
    app, client = _setup(tmp_path)
    try:
        persona = client.post(
            "/api/open-api/personas",
            json={"name": "周报助手", "system_prompt": "你负责写周报"},
        )
        assert persona.status_code == 200
        created = client.post(
            "/api/channel-plugins/instances",
            json={"type_id": "script_api", "name": "脚本甲", "persona_id": persona.json()["id"]},
        )
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["type_id"] == SCRIPT_API_TYPE_ID
        assert body["token"].startswith("lc_live_")
        assert body["role_id"].startswith(API_ROLE_PREFIX)

        chat = client.post(
            "/api/v1/chat",
            headers=_auth(body["token"]),
            json={"message": "投影后还能调吗"},
        )
        assert chat.status_code == 200, chat.text
        assert chat.json()["status"] == "completed"
        conv = app.state.container.conversations.get(chat.json()["conversation_id"])
        assert conv["origin"] == "api"
        assert conv["api_key_id"] == body["id"]
        assert conv["channel_instance_id"] == body["id"]
        assert conv["role_id"] == body["role_id"]

        coming = client.post(
            "/api/channel-plugins/instances",
            json={
                "type_id": "feishu",
                "name": "飞书甲",
                "config": {"app_id": "cli_test"},
                "secrets": {"app_secret": "secret-value"},
            },
        )
        assert coming.status_code == 200, coming.text
        feishu = coming.json()
        assert feishu["type_id"] == "feishu"
        assert feishu["role_id"].startswith(EXT_ROLE_PREFIX)
        assert feishu["enabled"] is True
        assert feishu["secrets"]["app_secret"] != "secret-value"
        assert "secret-value" not in coming.text
    finally:
        _close(client)


def test_hidden_channel_role_stays_off_sidebar(tmp_path):
    _app, client = _setup(tmp_path)
    try:
        created = client.post(
            "/api/channel-plugins/instances",
            json={"type_id": "script_api", "name": "脚本隐"},
        )
        assert created.status_code == 200
        role_id = created.json()["role_id"]
        roles = client.get("/api/roles").json()["roles"]
        assert all(item["id"] != role_id for item in roles)
        assert client.get(f"/api/roles/{role_id}").status_code == 404
    finally:
        _close(client)


def test_script_credential_copyable_after_create(tmp_path):
    _app, client = _setup(tmp_path)
    try:
        created = client.post(
            "/api/channel-plugins/instances",
            json={"type_id": "script_api", "name": "可复制"},
        )
        assert created.status_code == 200, created.text
        body = created.json()
        token = body["token"]
        inst_id = body["id"]
        listed = client.get("/api/channel-plugins/instances")
        assert listed.status_code == 200
        assert token not in listed.text
        assert "key_plaintext" not in listed.text
        cred = client.get(f"/api/channel-plugins/instances/{inst_id}/credential")
        assert cred.status_code == 200, cred.text
        payload = cred.json()
        assert payload["kind"] == "token"
        assert payload["can_copy_full"] is True
        assert payload["copy_text"] == token
        assert payload["token"] == token
    finally:
        _close(client)


def test_legacy_script_credential_without_plaintext(tmp_path):
    kb = tmp_path / "knowledge"
    (kb / ".kb").mkdir(parents=True)
    raw = mint_api_key()
    kid = "oldcopy01"
    (kb / ".kb" / "api_keys.json").write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "id": kid,
                        "name": "旧密钥",
                        "hash": hash_api_key(raw),
                        "prefix": raw[:12],
                        "persona_id": None,
                        "role_id": f"{API_ROLE_PREFIX}{kid}",
                        "revoked": False,
                        "created_at": "2026-09-01T00:00:00+00:00",
                        "last_used_at": None,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _app, client = _setup(tmp_path)
    try:
        cred = client.get(f"/api/channel-plugins/instances/{kid}/credential")
        assert cred.status_code == 200, cred.text
        payload = cred.json()
        assert payload["can_copy_full"] is False
        assert payload["copy_text"] == ""
        assert payload["prefix"] == raw[:12]
        assert raw not in cred.text
    finally:
        _close(client)


def test_feishu_credential_copy_includes_app_id(tmp_path):
    _app, client = _setup(tmp_path)
    try:
        created = client.post(
            "/api/channel-plugins/instances",
            json={
                "type_id": "feishu",
                "name": "飞书凭证",
                "config": {"app_id": "cli_copy", "ingress": "websocket"},
                "secrets": {"app_secret": "secret-value"},
            },
        )
        assert created.status_code == 200, created.text
        inst_id = created.json()["id"]
        listed = client.get("/api/channel-plugins/instances")
        assert "secret-value" not in listed.text
        cred = client.get(f"/api/channel-plugins/instances/{inst_id}/credential")
        assert cred.status_code == 200, cred.text
        payload = cred.json()
        assert payload["kind"] == "secrets"
        assert payload["can_copy_full"] is True
        assert "cli_copy" in payload["copy_text"]
        assert "secret-value" in payload["copy_text"]
    finally:
        _close(client)


def test_store_delete_removes_instance(tmp_path):
    kb = tmp_path / "kb"
    store = ChannelInstanceStore(kb, api_keys=ApiKeyStore(kb))
    inst = store.create(
        type_id="feishu",
        name="飞书",
        persona_id="p1",
        role_id="ext_del01",
        config={"app_id": "cli_x"},
        secrets={"app_secret": "s"},
        enabled=False,
    )
    removed = store.delete(inst["id"])
    assert removed["id"] == inst["id"]
    assert store.list_all() == []


def test_delete_disabled_feishu_instance(tmp_path):
    _app, client = _setup(tmp_path)
    try:
        created = client.post(
            "/api/channel-plugins/instances",
            json={
                "type_id": "feishu",
                "name": "飞书待删",
                "config": {"app_id": "cli_del", "ingress": "websocket"},
                "secrets": {"app_secret": "secret-value"},
            },
        )
        assert created.status_code == 200, created.text
        inst_id = created.json()["id"]

        blocked = client.delete(f"/api/channel-plugins/instances/{inst_id}")
        assert blocked.status_code == 409, blocked.text
        assert "请先停用" in blocked.text
        still = client.get("/api/channel-plugins/instances").json()["instances"]
        assert any(item["id"] == inst_id for item in still)

        off = client.patch(
            f"/api/channel-plugins/instances/{inst_id}",
            json={"enabled": False},
        )
        assert off.status_code == 200, off.text
        assert off.json()["enabled"] is False

        deleted = client.delete(f"/api/channel-plugins/instances/{inst_id}")
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["deleted"] is True
        assert deleted.json()["id"] == inst_id
        gone = client.get("/api/channel-plugins/instances").json()["instances"]
        assert all(item["id"] != inst_id for item in gone)
        missing = client.delete(f"/api/channel-plugins/instances/{inst_id}")
        assert missing.status_code == 404
    finally:
        _close(client)


def test_script_delete_still_revokes_instead_of_removing(tmp_path):
    _app, client = _setup(tmp_path)
    try:
        created = client.post(
            "/api/channel-plugins/instances",
            json={"type_id": "script_api", "name": "脚本吊销"},
        )
        assert created.status_code == 200, created.text
        inst_id = created.json()["id"]
        revoked = client.delete(f"/api/channel-plugins/instances/{inst_id}")
        assert revoked.status_code == 200, revoked.text
        body = revoked.json()
        assert body["id"] == inst_id
        assert body["enabled"] is False
        listed = client.get("/api/channel-plugins/instances").json()["instances"]
        assert any(item["id"] == inst_id and item["enabled"] is False for item in listed)
    finally:
        _close(client)
