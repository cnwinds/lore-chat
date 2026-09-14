"""聊天通道 P1：飞书长连接、入站排队、origin 排除、按实例日志/用量。"""

from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from app.config import Settings
from app.engine.agent.prompts import MODE_API
from app.engine.agent.tool_catalog import select_tools
from app.engine.channel_plugins.feishu import FeishuAdapter
from app.engine.channel_plugins.feishu_frame import (
    FRAME_DATA,
    HEADER_TYPE,
    TYPE_EVENT,
    WsFrame,
    ping_frame,
)
from app.engine.channel_plugins.secret_mask import mask_secret, merge_secrets
from app.engine.channel_plugins.types import InboundEvent
from app.engine.roles import EXT_ROLE_PREFIX
from app.main import create_app
from app.models.llm import FakeLLMClient


def _text_llm() -> FakeLLMClient:
    return FakeLLMClient(
        chat_responses=["ok"] * 40,
        tool_responses=[{"content": "飞书助手已收到", "tool_calls": []}] * 40,
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


def _p2p_event(
    *,
    text: str = "你好",
    event_id: str = "evt-1",
    open_id: str = "ou_1",
    chat_id: str = "oc_1",
    chat_type: str = "p2p",
) -> dict:
    return {
        "schema": "2.0",
        "header": {"event_id": event_id, "event_type": "im.message.receive_v1"},
        "event": {
            "sender": {
                "sender_type": "user",
                "sender_id": {"open_id": open_id},
            },
            "message": {
                "message_id": "om_1",
                "chat_id": chat_id,
                "chat_type": chat_type,
                "message_type": "text",
                "content": '{"text":"%s"}' % text,
            },
        },
    }


def _create_feishu(client: TestClient, *, name: str = "飞书私聊", enabled: bool = True):
    r = client.post(
        "/api/channel-plugins/instances",
        json={
            "type_id": "feishu",
            "name": name,
            "config": {"app_id": "cli_test", "ingress": "websocket"},
            "secrets": {"app_secret": "plain-secret"},
            "enabled": enabled,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def _wait_drain(app, instance_id: str, timeout: float = 8.0) -> None:
    turns = app.state.container.channel_turns
    role_id = app.state.container.channel_instances.get(instance_id)["role_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        with turns._qlock:
            empty = not turns._queues.get(instance_id)
        task = turns._drain_tasks.get(instance_id)
        if empty and (task is None or task.done()) and not turns.role_busy(role_id):
            return
        time.sleep(0.05)
    raise AssertionError("channel drain timeout")


def test_feishu_adapter_normalizes_p2p_text():
    adapter = FeishuAdapter()
    event = adapter.parse_inbound(
        {"instance_id": "inst1", "body": _p2p_event(text="今晚开会")}
    )
    assert event.instance_id == "inst1"
    assert event.text == "今晚开会"
    assert event.event_id == "evt-1"
    assert event.external_user_id == "ou_1"
    assert event.external_chat_id == "oc_1"
    assert event.is_group is False


def test_feishu_adapter_ignores_group_and_non_text():
    adapter = FeishuAdapter()
    group = adapter.parse_inbound(
        {
            "instance_id": "i",
            "body": _p2p_event(chat_type="group", text="群里说一句"),
        }
    )
    assert group.is_group is True
    empty_type = adapter.parse_inbound(
        {
            "instance_id": "i",
            "body": {
                "header": {"event_id": "e2", "event_type": "im.message.receive_v1"},
                "event": {
                    "sender": {"sender_type": "user", "sender_id": {"open_id": "ou"}},
                    "message": {
                        "chat_type": "p2p",
                        "message_type": "image",
                        "content": "{}",
                    },
                },
            },
        }
    )
    assert empty_type.text == ""
    missing_chat = adapter.parse_inbound(
        {
            "instance_id": "i",
            "body": {
                "header": {"event_id": "e3", "event_type": "im.message.receive_v1"},
                "event": {
                    "sender": {"sender_type": "user", "sender_id": {"open_id": "ou"}},
                    "message": {"message_type": "text", "content": '{"text":"x"}'},
                },
            },
        }
    )
    assert missing_chat.is_group is True


def test_feishu_validate_websocket_without_public_url():
    adapter = FeishuAdapter()
    cfg = {"app_id": "cli_x", "ingress": "websocket"}
    sec = {"app_secret": "s"}
    status, detail = adapter.validate_config(
        cfg, sec, public_base_url=None, enabling=True
    )
    assert status == "enabled"
    assert detail is None


def test_feishu_webhook_save_without_public_url_is_not_error():
    adapter = FeishuAdapter()
    status, detail = adapter.validate_config(
        {"app_id": "cli_x", "ingress": "http_webhook"},
        {"app_secret": "s"},
        public_base_url=None,
        enabling=False,
    )
    assert status == "disabled"
    assert detail is None
    status, detail = adapter.validate_config(
        {"app_id": "cli_x", "ingress": "http_webhook"},
        {"app_secret": "s"},
        public_base_url=None,
        enabling=True,
    )
    assert status == "error"
    assert "公网根" in (detail or "")


def test_feishu_webhook_enable_with_public_url_still_error_in_p1():
    adapter = FeishuAdapter()
    status, detail = adapter.validate_config(
        {"app_id": "cli_x", "ingress": "http_webhook"},
        {"app_secret": "s"},
        public_base_url="https://example.com",
        enabling=True,
    )
    assert status == "error"
    assert "长连接" in (detail or "")


def test_secret_mask_and_merge():
    assert mask_secret("plain-secret") != "plain-secret"
    assert "***" in mask_secret("plain-secret")
    stored = {"app_secret": "real"}
    merged = merge_secrets(stored, {"app_secret": "pl***cret", "encrypt_key": ""})
    assert merged["app_secret"] == "real"
    merged = merge_secrets(stored, {"app_secret": "new-secret"})
    assert merged["app_secret"] == "new-secret"


def test_feishu_frame_roundtrip():
    payload = b'{"header":{"event_id":"e"}}'
    frame = WsFrame(
        seq_id=7,
        log_id=9,
        service=1,
        method=FRAME_DATA,
        headers=[(HEADER_TYPE, TYPE_EVENT)],
        payload=payload,
    )
    decoded = WsFrame.decode(frame.encode())
    assert decoded.seq_id == 7
    assert decoded.method == FRAME_DATA
    assert decoded.header(HEADER_TYPE) == TYPE_EVENT
    assert decoded.payload == payload
    ping = ping_frame(0)
    assert ping.header(HEADER_TYPE) == "ping"


def test_create_feishu_masks_secrets_and_uses_ext_role(tmp_path):
    _app, client = _setup(tmp_path)
    try:
        body = _create_feishu(client)
        assert body["role_id"].startswith(EXT_ROLE_PREFIX)
        assert body["secrets"]["app_secret"] != "plain-secret"
        assert "plain-secret" not in str(body)
        roles = client.get("/api/roles").json()["roles"]
        assert all(item["id"] != body["role_id"] for item in roles)
        assert client.get(f"/api/roles/{body['role_id']}").status_code == 404
        types = client.get("/api/channel-plugins/types").json()["types"]
        feishu = next(item for item in types if item["type_id"] == "feishu")
        assert feishu["available"] is True
        assert feishu["ingress"] == "websocket"
        assert feishu["needs_public_url"] is False
    finally:
        _close(client)


def test_webhook_save_missing_public_url_is_not_400(tmp_path):
    _app, client = _setup(tmp_path)
    try:
        saved = client.post(
            "/api/channel-plugins/instances",
            json={
                "type_id": "feishu",
                "name": "回调飞书",
                "enabled": False,
                "config": {"app_id": "cli_x", "ingress": "http_webhook"},
                "secrets": {"app_secret": "s"},
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["status"] == "disabled"
        enabled = client.patch(
            f"/api/channel-plugins/instances/{saved.json()['id']}",
            json={"enabled": True},
        )
        assert enabled.status_code == 200, enabled.text
        body = enabled.json()
        assert body["status"] == "error"
        assert "公网根" in (body.get("status_detail") or "")
    finally:
        _close(client)


def test_enqueue_duplicate_and_disabled(tmp_path):
    app, client = _setup(tmp_path)
    try:
        inst = _create_feishu(client)
        adapter = FeishuAdapter()
        event = adapter.parse_inbound(
            {"instance_id": inst["id"], "body": _p2p_event(event_id="same")}
        )
        turns = app.state.container.channel_turns
        sent: list[str] = []
        app.state.container.channel_registry.get("feishu").send_outbound = (
            lambda _i, text, **_k: sent.append(text)
        )
        assert turns.enqueue_now(event)["status"] == "accepted"
        _wait_drain(app, inst["id"])
        assert turns.enqueue_now(event)["status"] == "duplicate"
        client.patch(
            f"/api/channel-plugins/instances/{inst['id']}",
            json={"enabled": False},
        )
        other = adapter.parse_inbound(
            {"instance_id": inst["id"], "body": _p2p_event(event_id="later")}
        )
        assert turns.enqueue_now(other)["status"] == "ignored"
        logs = client.get(
            f"/api/channel-plugins/instances/{inst['id']}/logs"
        ).json()["items"]
        kinds = {item["kind"] for item in logs}
        assert "inbound_duplicate" in kinds
        assert "turn_done" in kinds
        assert sent == ["飞书助手已收到"]
        assert "还在处理" not in "".join(sent)
    finally:
        _close(client)


def test_same_instance_second_message_queues(tmp_path):
    gate = threading.Event()

    class GatedLLM(FakeLLMClient):
        def chat_with_tools(self, messages, tools, *, big=True, temperature=0.2):
            gate.wait(timeout=10)
            return super().chat_with_tools(
                messages, tools, big=big, temperature=temperature
            )

    llm = GatedLLM(
        chat_responses=["ok"] * 20,
        tool_responses=[
            {"content": "第一句", "tool_calls": []},
            {"content": "第二句", "tool_calls": []},
        ]
        * 4,
        embed_dim=8,
    )
    app, client = _setup(tmp_path, llm=llm)
    try:
        inst = _create_feishu(client)
        adapter = FeishuAdapter()
        turns = app.state.container.channel_turns
        sent: list[str] = []
        app.state.container.channel_registry.get("feishu").send_outbound = (
            lambda _i, text, **_k: sent.append(text)
        )
        first = adapter.parse_inbound(
            {"instance_id": inst["id"], "body": _p2p_event(event_id="a", text="一")}
        )
        second = adapter.parse_inbound(
            {"instance_id": inst["id"], "body": _p2p_event(event_id="b", text="二")}
        )
        assert turns.enqueue_now(first)["status"] == "accepted"
        deadline = time.time() + 5
        while time.time() < deadline and not turns.role_busy(inst["role_id"]):
            time.sleep(0.02)
        assert turns.role_busy(inst["role_id"])
        assert turns.enqueue_now(second)["status"] == "accepted"
        with turns._qlock:
            queued = list(turns._queues.get(inst["id"]) or [])
        assert len(queued) == 1
        running = [
            t
            for t in app.state.container.conversations.list_running_turns()
            if app.state.container.conversations.get_role_id(t["conversation_id"])
            == inst["role_id"]
        ]
        assert len(running) == 1
        gate.set()
        _wait_drain(app, inst["id"])
        assert sent == ["第一句", "第二句"]
        assert "还在处理" not in "".join(sent)
    finally:
        gate.set()
        _close(client)


def test_feishu_origin_excluded_from_memory_and_sidebar_tip(tmp_path):
    app, client = _setup(tmp_path)
    try:
        inst = _create_feishu(client)
        adapter = FeishuAdapter()
        app.state.container.channel_registry.get("feishu").send_outbound = (
            lambda *_a, **_k: None
        )
        event = adapter.parse_inbound(
            {"instance_id": inst["id"], "body": _p2p_event(text="我叫小明")}
        )
        assert app.state.container.channel_turns.enqueue_now(event)["status"] == "accepted"
        _wait_drain(app, inst["id"])
        key = f"feishu:{inst['id']}:dm:ou_1"
        cid = app.state.container.channel_turns.runtime_store.get_thread(
            inst["id"], key
        )
        assert cid
        conv = app.state.container.conversations.get(cid)
        assert conv["origin"] == "feishu"
        assert conv["channel_instance_id"] == inst["id"]
        row = app.state.container.conversations.conn.execute(
            "SELECT memory_dirty FROM conversations WHERE id = ?", (cid,)
        ).fetchone()
        assert int(row["memory_dirty"] or 0) == 0
        assert inst["role_id"] not in app.state.container.conversations.last_active_at_by_role()
        assert inst["role_id"] not in app.state.container.conversations.last_reply_preview_by_role()
        sidebar = client.get("/api/roles").json()["roles"]
        assert all(item["id"] != inst["role_id"] for item in sidebar)
    finally:
        _close(client)


def test_shared_persona_live_reference(tmp_path):
    _app, client = _setup(tmp_path)
    try:
        persona = client.post(
            "/api/open-api/personas",
            json={"name": "共用", "system_prompt": "旧提示词"},
        ).json()
        script = client.post(
            "/api/channel-plugins/instances",
            json={
                "type_id": "script_api",
                "name": "脚本共用",
                "persona_id": persona["id"],
            },
        ).json()
        feishu = client.post(
            "/api/channel-plugins/instances",
            json={
                "type_id": "feishu",
                "name": "飞书共用",
                "persona_id": persona["id"],
                "config": {"app_id": "cli_x"},
                "secrets": {"app_secret": "s"},
            },
        ).json()
        client.patch(
            f"/api/open-api/personas/{persona['id']}",
            json={"system_prompt": "新提示词"},
        )
        updated = client.get("/api/open-api/personas").json()["personas"]
        prompt = next(p for p in updated if p["id"] == persona["id"])["system_prompt"]
        assert prompt == "新提示词"
        listed = client.get("/api/channel-plugins/instances").json()["instances"]
        by_id = {item["id"]: item for item in listed}
        assert by_id[script["id"]]["persona_id"] == persona["id"]
        assert by_id[feishu["id"]]["persona_id"] == persona["id"]
        assert by_id[feishu["id"]]["persona"]["system_prompt"] == "新提示词"
        assert by_id[script["id"]]["persona"]["system_prompt"] == "新提示词"
    finally:
        _close(client)


def test_instance_logs_and_usage_endpoints(tmp_path):
    app, client = _setup(tmp_path)
    try:
        inst = _create_feishu(client)
        other = _create_feishu(client, name="另一路")
        rec = getattr(app.state.container.llm, "usage_recorder", None)
        if rec is None:
            from app.engine.usage.recorder import UsageRecorder

            rec = UsageRecorder(app.state.container._usage_store)
        rec.record(
            model="m",
            kind="chat",
            status="ok",
            tokens_known=True,
            total_tokens=11,
            channel_instance_id=inst["id"],
            conversation_id="c-a",
        )
        rec.record(
            model="m",
            kind="chat",
            status="ok",
            tokens_known=True,
            total_tokens=99,
            channel_instance_id=other["id"],
            conversation_id="c-b",
        )
        usage = client.get(
            f"/api/channel-plugins/instances/{inst['id']}/usage"
        ).json()
        assert usage["totals"]["calls"] == 1
        assert usage["totals"]["total_tokens"] == 11
        scoped = client.get(
            "/api/usage/summary",
            params={"channel_instance_id": inst["id"], "granularity": "month"},
        ).json()
        assert scoped["totals"]["calls"] == 1
        app.state.container.channel_turns.runtime_store.add_log(
            inst["id"], kind="outbound_retry", message="暂时失败", level="warn"
        )
        logs = client.get(
            f"/api/channel-plugins/instances/{inst['id']}/logs"
        ).json()["items"]
        assert any(item["kind"] == "outbound_retry" for item in logs)
        other_logs = client.get(
            f"/api/channel-plugins/instances/{other['id']}/logs"
        ).json()["items"]
        assert all(item["kind"] != "outbound_retry" for item in other_logs)
    finally:
        _close(client)


def test_mode_api_keeps_sandbox_for_channel_turns():
    names = {
        item["function"]["name"]
        for item in select_tools(MODE_API, web_enabled=False, sandbox_enabled=True)
    }
    assert "sandbox_run" in names
    assert "write_doc" not in names
    assert "send_message" not in names
    assert "manage_memory" not in names


def test_enqueue_group_does_not_start_turn(tmp_path):
    app, client = _setup(tmp_path)
    try:
        inst = _create_feishu(client)
        event = FeishuAdapter().parse_inbound(
            {
                "instance_id": inst["id"],
                "body": _p2p_event(chat_type="group", event_id="g1"),
            }
        )
        assert event.is_group is True
        out = app.state.container.channel_turns.enqueue_now(event)
        assert out["status"] == "ignored"
        convs = app.state.container.conversations.list_all(role_id=inst["role_id"])
        assert convs == []
    finally:
        _close(client)
