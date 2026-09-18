"""对外聊天 API：人设可共享，每把 Key 一个独立隐藏角色。"""

import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.engine.agent.prompts import MODE_API
from app.engine.agent.tool_catalog import select_tools
from app.engine.roles import API_ROLE_PREFIX, VISIBILITY_HIDDEN
from app.main import create_app
from app.models.llm import FakeLLMClient, ToolCall


def _text_llm() -> FakeLLMClient:
    return FakeLLMClient(
        chat_responses=["ok"] * 40,
        tool_responses=[{"content": "脚本助手已收到", "tool_calls": []}] * 40,
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


def _create_key(client: TestClient, *, name: str, persona_id: str | None = None):
    if persona_id is None:
        persona = client.post(
            "/api/open-api/personas",
            json={"name": "周报助手", "system_prompt": "你负责写周报"},
        )
        assert persona.status_code == 200, persona.text
        persona_id = persona.json()["id"]
    key = client.post(
        "/api/open-api/keys",
        json={"name": name, "persona_id": persona_id},
    )
    assert key.status_code == 200, key.text
    body = key.json()
    assert body["token"].startswith("lc_live_")
    assert body["role_id"].startswith(API_ROLE_PREFIX)
    assert body["persona_id"] == persona_id
    return body, persona_id


def test_v1_requires_bearer_not_cookie(tmp_path):
    app, client = _setup(tmp_path)
    try:
        missing = client.post("/api/v1/chat", json={"message": "hi"})
        assert missing.status_code == 401
        assert missing.json()["code"] == "api_key_required"

        bad = client.post(
            "/api/v1/chat",
            headers=_auth("lc_live_not-a-real-key"),
            json={"message": "hi"},
        )
        assert bad.status_code == 401
        assert bad.json()["code"] == "api_key_invalid"

        key, _ = _create_key(client, name="脚本")
        with TestClient(app) as anon:
            r = anon.get(
                "/api/open-api/keys",
                headers=_auth(key["token"]),
            )
            assert r.status_code == 401
            assert r.json()["code"] == "auth_required"
    finally:
        _close(client)


def test_hidden_worker_role_stays_off_sidebar(tmp_path):
    _app, client = _setup(tmp_path)
    try:
        key, _ = _create_key(client, name="脚本甲")
        roles = client.get("/api/roles").json()["roles"]
        assert all(not item["id"].startswith(API_ROLE_PREFIX) for item in roles)
        assert all(item["id"] != key["role_id"] for item in roles)

        assert client.get(f"/api/roles/{key['role_id']}").status_code == 404
        assert (
            client.post(f"/api/roles/{key['role_id']}/ensure-active").status_code
            == 404
        )
        tl = client.get(
            f"/api/roles/{key['role_id']}/timeline",
            params={"limit": 20, "message_limit": 0},
        )
        assert tl.status_code == 200
        assert tl.json()["role_id"] == key["role_id"]
    finally:
        _close(client)


def test_two_keys_share_persona_but_isolate_roles_and_chats(tmp_path):
    app, client = _setup(tmp_path)
    try:
        key_a, persona_id = _create_key(client, name="同事甲")
        key_b, _ = _create_key(client, name="同事乙", persona_id=persona_id)
        assert key_a["role_id"] != key_b["role_id"]
        assert key_a["persona_id"] == key_b["persona_id"]

        ra = client.post(
            "/api/v1/chat",
            headers=_auth(key_a["token"]),
            json={"message": "甲的问题"},
        )
        rb = client.post(
            "/api/v1/chat",
            headers=_auth(key_b["token"]),
            json={"message": "乙的问题"},
        )
        assert ra.status_code == 200, ra.text
        assert rb.status_code == 200, rb.text
        body_a, body_b = ra.json(), rb.json()
        assert body_a["status"] == "completed"
        assert body_b["status"] == "completed"
        assert body_a["message"]["content"]
        assert body_a["conversation_id"] != body_b["conversation_id"]

        conv_a = app.state.container.conversations.get(body_a["conversation_id"])
        conv_b = app.state.container.conversations.get(body_b["conversation_id"])
        assert conv_a["origin"] == "api"
        assert conv_b["origin"] == "api"
        assert conv_a["api_key_id"] == key_a["id"]
        assert conv_b["api_key_id"] == key_b["id"]
        assert conv_a["role_id"] == key_a["role_id"]
        assert conv_b["role_id"] == key_b["role_id"]

        listed_a = client.get(
            "/api/v1/conversations", headers=_auth(key_a["token"])
        ).json()["conversations"]
        ids_a = {item["id"] for item in listed_a}
        assert body_a["conversation_id"] in ids_a
        assert body_b["conversation_id"] not in ids_a

        steal = client.post(
            "/api/v1/chat",
            headers=_auth(key_b["token"]),
            json={
                "message": "偷看",
                "conversation_id": body_a["conversation_id"],
            },
        )
        assert steal.status_code == 404
    finally:
        _close(client)


def test_persona_live_reference_after_update(tmp_path):
    app, client = _setup(tmp_path)
    try:
        key, persona_id = _create_key(client, name="脚本")
        patched = client.patch(
            f"/api/open-api/personas/{persona_id}",
            json={"system_prompt": "只说四川话"},
        )
        assert patched.status_code == 200
        cid = app.state.container.conversations.create(
            role_id=key["role_id"],
            origin="api",
            api_key_id=key["id"],
        )
        block = app.state.container.chat_runner.turn_hub._role_system_prompt_for(cid)
        assert "只说四川话" in block
        assert "你负责写周报" not in block
    finally:
        _close(client)


def test_same_key_second_turn_is_409(tmp_path):
    app, client = _setup(tmp_path)
    try:
        key, _ = _create_key(client, name="脚本")
        first = client.post(
            "/api/v1/chat",
            headers=_auth(key["token"]),
            json={"message": "第一枪"},
        )
        assert first.status_code == 200, first.text
        cid = first.json()["conversation_id"]
        app.state.container.conversations.begin_turn(cid, "占住", "hold-1")
        second = client.post(
            "/api/v1/chat",
            headers=_auth(key["token"]),
            json={"message": "第二枪"},
        )
        assert second.status_code == 409
        assert second.json()["detail"]["code"] == "turn_in_progress"
    finally:
        _close(client)


def test_revoke_blocks_v1_but_history_remains(tmp_path):
    _app, client = _setup(tmp_path)
    try:
        key, persona_id = _create_key(client, name="脚本")
        chat = client.post(
            "/api/v1/chat",
            headers=_auth(key["token"]),
            json={"message": "留下记录"},
        )
        assert chat.status_code == 200
        blocked = client.delete(f"/api/open-api/personas/{persona_id}")
        assert blocked.status_code == 400

        revoked = client.delete(f"/api/open-api/keys/{key['id']}")
        assert revoked.status_code == 200
        assert revoked.json()["revoked"] is True

        denied = client.post(
            "/api/v1/chat",
            headers=_auth(key["token"]),
            json={"message": "还能调吗"},
        )
        assert denied.status_code == 401

        tl = client.get(
            f"/api/roles/{key['role_id']}/timeline",
            params={"limit": 20, "message_limit": 0},
        )
        assert tl.status_code == 200
        texts = [
            msg.get("text")
            for seg in tl.json().get("segments") or []
            for msg in seg.get("messages") or []
        ]
        assert any(text and "留下记录" in text for text in texts)
    finally:
        _close(client)


def test_select_tools_api_mode_drops_writes():
    names = {
        item["function"]["name"]
        for item in select_tools(MODE_API, web_enabled=False, sandbox_enabled=True)
    }
    assert "write_doc" not in names
    assert "write_kb_file" not in names
    assert "publish_from_sandbox" not in names
    assert "create_role" not in names
    assert "manage_memory" not in names
    assert "send_message" not in names
    assert "list_rooms" not in names
    assert "create_room" not in names
    assert "list_groups" not in names
    assert "create_group" not in names
    assert "update_group" not in names
    assert "delete_group" not in names
    assert "sandbox_run" in names
    assert "search_kb" in names


def test_hidden_role_and_persona_store(tmp_path):
    from app.engine.roles import RoleStore

    store = RoleStore(tmp_path / "roles")
    persona = store.create_persona(name="共用", system_prompt="提示词")
    hidden = store.create(
        name="工作角色",
        visibility=VISIBILITY_HIDDEN,
        role_id=f"{API_ROLE_PREFIX}abcd",
        persona_id=persona["id"],
        onboarding_status="completed",
    )
    assert hidden["visibility"] == VISIBILITY_HIDDEN
    assert hidden["onboarding_status"] == "completed"
    assert all(r["id"] != hidden["id"] for r in store.list_all(visibility="sidebar"))
    assert any(r["id"] == hidden["id"] for r in store.list_all())
    assert store.get_persona(persona["id"])["system_prompt"] == "提示词"


def _parse_sse_events(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        event_type = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event_type and data is not None:
            events.append((event_type, data))
    return events


def test_v1_chat_stream_is_sse_and_hides_trace_by_default(tmp_path):
    llm = FakeLLMClient(
        chat_responses=["ok"] * 20,
        tool_responses=[
            {"content": "流式已收到", "think": "先想一步", "tool_calls": []}
        ]
        * 20,
        embed_dim=8,
    )
    app, client = _setup(tmp_path, llm=llm)
    try:
        key, _ = _create_key(client, name="脚本")
        r = client.post(
            "/api/v1/chat",
            headers=_auth(key["token"]),
            json={"message": "流式一下", "stream": True},
        )
        assert r.status_code == 200, r.text
        assert "text/event-stream" in r.headers.get("content-type", "")
        events = _parse_sse_events(r.text)
        types = [t for t, _ in events]
        assert types[0] == "start"
        assert "text_delta" in types
        assert "done" in types
        assert "think_delta" not in types
        assert "tool_start" not in types
        assert "timeline_state" not in types
        start = events[0][1]
        done = next(data for t, data in events if t == "done")
        assert start["conversation_id"] == done["conversation_id"]
        assert start["turn_id"] == done["turn_id"]
        assert r.headers.get("X-Turn-Id") == done["turn_id"]
        assert r.headers.get("X-Conversation-Id") == done["conversation_id"]
        assert done["status"] == "completed"
        assert "流式已收到" in (done.get("message") or {}).get("content", "")
        assert "assistant" not in done
        text = "".join(
            data.get("delta") or "" for t, data in events if t == "text_delta"
        )
        assert "流式已收到" in text
        assert "先想一步" not in text
    finally:
        _close(client)


def test_v1_chat_stream_emits_thinking_when_enabled(tmp_path):
    llm = FakeLLMClient(
        chat_responses=["ok"] * 20,
        tool_responses=[
            {"content": "打开思考", "think": "先想一步", "tool_calls": []}
        ]
        * 20,
        embed_dim=8,
    )
    app, client = _setup(tmp_path, llm=llm)
    try:
        key, _ = _create_key(client, name="脚本")
        patched = client.patch(
            f"/api/channel-plugins/instances/{key['id']}",
            json={"show_thinking": True},
        )
        assert patched.status_code == 200, patched.text
        r = client.post(
            "/api/v1/chat",
            headers=_auth(key["token"]),
            json={"message": "带思考", "stream": True},
        )
        assert r.status_code == 200, r.text
        events = _parse_sse_events(r.text)
        types = [t for t, _ in events]
        assert "think_delta" in types
        think = "".join(
            data.get("delta") or "" for t, data in events if t == "think_delta"
        )
        assert "先想一步" in think
        assert "timeline_state" not in types
    finally:
        _close(client)


def test_v1_chat_stream_emits_tools_when_enabled(tmp_path):
    llm = FakeLLMClient(
        chat_responses=["ok"] * 20,
        tool_responses=[
            {
                "content": None,
                "tool_calls": [
                    ToolCall(
                        id="1",
                        name="search_kb",
                        arguments={"query": "周报"},
                    )
                ],
            },
            {"content": "检索结论", "tool_calls": []},
        ]
        * 10,
        embed_dim=8,
    )
    _app, client = _setup(tmp_path, llm=llm)
    try:
        key, _ = _create_key(client, name="脚本")
        hidden = client.post(
            "/api/v1/chat",
            headers=_auth(key["token"]),
            json={"message": "先关着", "stream": True},
        )
        assert hidden.status_code == 200, hidden.text
        hidden_types = [t for t, _ in _parse_sse_events(hidden.text)]
        assert "tool_start" not in hidden_types
        assert "tool_result" not in hidden_types
        assert "timeline_state" not in hidden_types

        patched = client.patch(
            f"/api/channel-plugins/instances/{key['id']}",
            json={"show_tool_output": True},
        )
        assert patched.status_code == 200, patched.text
        r = client.post(
            "/api/v1/chat",
            headers=_auth(key["token"]),
            json={"message": "再开工具", "stream": True},
        )
        assert r.status_code == 200, r.text
        events = _parse_sse_events(r.text)
        types = [t for t, _ in events]
        assert "tool_start" in types
        assert "tool_result" in types
        assert "timeline_state" not in types
        start = next(data for t, data in events if t == "tool_start")
        assert start["tool"] == "search_kb"
        assert start.get("query") == "周报"
        assert "input" not in start
        done = next(data for t, data in events if t == "done")
        assert "检索结论" in (done.get("message") or {}).get("content", "")
    finally:
        _close(client)


def test_v1_chat_stream_rejects_empty_message(tmp_path):
    _app, client = _setup(tmp_path)
    try:
        key, _ = _create_key(client, name="脚本")
        r = client.post(
            "/api/v1/chat",
            headers=_auth(key["token"]),
            json={"message": "  ", "stream": True},
        )
        assert r.status_code == 400
    finally:
        _close(client)
