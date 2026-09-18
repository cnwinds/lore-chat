"""聊天通道 P2：Slack / 企微 / 钉钉、群 @ 规则、attachments、needs_input 降级。"""

from __future__ import annotations

import base64
import os
import time

from fastapi.testclient import TestClient

from app.config import Settings
from app.engine.agent.prompts import MODE_API
from app.engine.agent.tool_catalog import select_tools
from app.engine.channel_plugins.aes_pkcs7 import (
    decode_aes_key,
    decrypt_msg,
    encrypt_msg,
    signature,
)
from app.engine.channel_plugins.dingtalk import DingtalkAdapter
from app.engine.channel_plugins.feishu import FeishuAdapter
from app.engine.channel_plugins.group_policy import (
    compose_im_reply,
    sandbox_allowed_for,
    should_enqueue_group,
    thread_external_key,
)
from app.engine.channel_plugins.media import materialize_media
from app.engine.channel_plugins.slack import SlackAdapter
from app.engine.channel_plugins.types import InboundEvent, InboundMedia
from app.engine.channel_plugins.wecom import WecomAdapter
from app.main import create_app
from app.models.llm import FakeLLMClient


def _text_llm() -> FakeLLMClient:
    return FakeLLMClient(
        chat_responses=["ok"] * 40,
        tool_responses=[{"content": "通道已收到", "tool_calls": []}] * 40,
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


def _aes_key_b64() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii").rstrip("=")


def _feishu_group(*, text="群里说一句", event_id="g1", mentions=None, parent_id=None, message_id="om_g"):
    message = {
        "message_id": message_id,
        "chat_id": "oc_group",
        "chat_type": "group",
        "message_type": "text",
        "content": '{"text":"%s"}' % text,
    }
    if mentions:
        message["mentions"] = mentions
    if parent_id:
        message["parent_id"] = parent_id
        message["root_id"] = parent_id
    return {
        "schema": "2.0",
        "header": {"event_id": event_id, "event_type": "im.message.receive_v1"},
        "event": {
            "sender": {
                "sender_type": "user",
                "sender_id": {"open_id": "ou_user"},
            },
            "message": message,
        },
    }


def test_should_enqueue_group_bare_mention_quote_thread():
    bare = InboundEvent(instance_id="i", text="hi", is_group=True)
    ok, reason = should_enqueue_group(bare)
    assert ok is False
    assert reason == "group_bare"

    mentioned = InboundEvent(
        instance_id="i", text="hi", is_group=True, mentioned_bot=True
    )
    assert should_enqueue_group(mentioned)[0] is True

    quoted = InboundEvent(instance_id="i", text="hi", is_group=True, quoted=True)
    assert should_enqueue_group(quoted)[1] == "quote"

    mapped = InboundEvent(
        instance_id="i",
        text="续",
        is_group=True,
        external_chat_id="C1",
        external_thread_id="111.222",
    )
    assert should_enqueue_group(mapped, has_mapped_thread=True)[1] == "thread"


def test_sandbox_group_defaults_off_until_allowlist():
    event = InboundEvent(
        instance_id="i",
        text="hi",
        is_group=True,
        external_user_id="U1",
    )
    inst = {"config": {}}
    assert sandbox_allowed_for(inst, event) is False
    inst = {"config": {"sandbox_allow_senders": "U1, U2"}}
    assert sandbox_allowed_for(inst, event) is True
    dm = InboundEvent(instance_id="i", text="hi", is_group=False, external_user_id="U9")
    assert sandbox_allowed_for({"config": {}}, dm) is True


def test_compose_im_reply_degrades_ask_user():
    assistant = {
        "text": "",
        "timeline": [
            {
                "type": "tool",
                "tool": "ask_user",
                "question": "先做哪一块？",
                "options": [
                    {"id": "a", "label": "检索"},
                    {"id": "b", "label": "落库"},
                ],
            }
        ],
    }
    text = compose_im_reply(assistant)
    assert "先做哪一块？" in text
    assert "检索" in text
    assert "请回复选项" in text


def test_compose_im_reply_omits_thinking_and_tools_by_default():
    assistant = {
        "text": "最终答案",
        "timeline": [
            {"type": "think", "content": "先想一步"},
            {
                "type": "tool",
                "tool": "read_doc",
                "label": "读文档",
                "query": "笔记.md",
                "summary": "找到了",
            },
        ],
    }
    text = compose_im_reply(assistant)
    assert text == "最终答案"
    assert "先想一步" not in text
    assert "读文档" not in text


def test_compose_im_reply_includes_thinking_and_tools_when_enabled():
    assistant = {
        "text": "最终答案",
        "timeline": [
            {"type": "think", "content": "先想一步"},
            {
                "type": "parallel",
                "children": [
                    {
                        "type": "tool",
                        "tool": "read_doc",
                        "label": "读文档",
                        "query": "笔记.md",
                        "summary": "找到了",
                    }
                ],
            },
            {
                "type": "tool",
                "tool": "ask_user",
                "question": "接下来？",
                "options": [{"id": "a", "label": "继续"}],
            },
        ],
    }
    thinking = compose_im_reply(assistant, show_thinking=True)
    assert "思考" in thinking
    assert "先想一步" in thinking
    assert "最终答案" in thinking
    assert "读文档" not in thinking
    assert "接下来？" in thinking

    tools = compose_im_reply(assistant, show_tool_output=True)
    assert "工具 · 读文档" in tools
    assert "笔记.md" in tools
    assert "找到了" in tools
    assert "先想一步" not in tools
    assert "接下来？" in tools
    assert "请回复选项" in tools

    both = compose_im_reply(
        assistant, show_thinking=True, show_tool_output=True
    )
    assert both.index("先想一步") < both.index("读文档")
    assert both.index("读文档") < both.index("最终答案")


def test_materialize_media_writes_upload_attachment(tmp_path):
    kb = tmp_path / "knowledge"
    kb.mkdir()
    paths = materialize_media(
        kb,
        "inst1",
        [InboundMedia(filename="shot.png", kind="image", data=b"\x89PNG")],
    )
    assert len(paths) == 1
    assert paths[0].startswith("媒体/上传/")
    assert (kb / paths[0]).read_bytes() == b"\x89PNG"


def test_slack_parse_app_mention_vs_channel_bare():
    adapter = SlackAdapter()
    mention = adapter.parse_inbound(
        {
            "instance_id": "s1",
            "body": {
                "event_id": "Ev1",
                "event": {
                    "type": "app_mention",
                    "user": "U1",
                    "channel": "C1",
                    "ts": "111.1",
                    "text": "<@B0> 帮忙看下",
                    "channel_type": "channel",
                },
            },
        }
    )
    assert mention.is_group is True
    assert mention.mentioned_bot is True
    assert mention.external_thread_id == "111.1"

    bare = adapter.parse_inbound(
        {
            "instance_id": "s1",
            "body": {
                "event_id": "Ev2",
                "event": {
                    "type": "message",
                    "user": "U1",
                    "channel": "C1",
                    "ts": "222.2",
                    "text": "随便聊聊",
                    "channel_type": "channel",
                },
            },
        }
    )
    assert bare.is_group is True
    assert bare.mentioned_bot is False
    assert should_enqueue_group(bare)[0] is False

    dm = adapter.parse_inbound(
        {
            "instance_id": "s1",
            "body": {
                "event_id": "Ev3",
                "event": {
                    "type": "message",
                    "user": "U1",
                    "channel": "D1",
                    "ts": "333.3",
                    "text": "私聊",
                    "channel_type": "im",
                },
            },
        }
    )
    assert dm.is_group is False
    assert should_enqueue_group(dm)[0] is True


def test_slack_thread_reply_without_mention_needs_mapping():
    adapter = SlackAdapter()
    reply = adapter.parse_inbound(
        {
            "instance_id": "s1",
            "body": {
                "event_id": "Ev4",
                "event": {
                    "type": "message",
                    "user": "U1",
                    "channel": "C1",
                    "ts": "444.4",
                    "thread_ts": "111.1",
                    "text": "跟一句",
                    "channel_type": "channel",
                },
            },
        }
    )
    assert reply.quoted is False
    assert reply.mentioned_bot is False
    assert should_enqueue_group(reply)[0] is False
    assert should_enqueue_group(reply, has_mapped_thread=True)[0] is True
    key = thread_external_key("slack", "s1", reply)
    assert key.endswith(":group:C1:111.1")


def test_dingtalk_group_requires_at():
    adapter = DingtalkAdapter()
    bare = adapter.parse_inbound(
        {
            "instance_id": "d1",
            "body": {
                "data": {
                    "conversationType": "2",
                    "conversationId": "cid1",
                    "senderStaffId": "staff1",
                    "msgId": "m1",
                    "text": {"content": "群里说一句"},
                    "isInAtList": False,
                    "sessionWebhook": "https://oapi.dingtalk.com/robot/send?token=x",
                }
            },
        }
    )
    assert bare.is_group is True
    assert bare.mentioned_bot is False
    at = adapter.parse_inbound(
        {
            "instance_id": "d1",
            "body": {
                "data": {
                    "conversationType": "2",
                    "conversationId": "cid1",
                    "senderStaffId": "staff1",
                    "msgId": "m2",
                    "text": {"content": "@机器人 帮忙"},
                    "isInAtList": True,
                    "sessionWebhook": "https://oapi.dingtalk.com/robot/send?token=x",
                }
            },
        }
    )
    assert at.mentioned_bot is True
    assert at.extra.get("session_webhook")


def test_wecom_aes_roundtrip_and_group_mention():
    adapter = WecomAdapter()
    key_b64 = _aes_key_b64()
    key = decode_aes_key(key_b64)
    inner = (
        "<xml><ToUserName>ww</ToUserName><FromUserName>user1</FromUserName>"
        "<MsgType>text</MsgType><Content>你好</Content><MsgId>9</MsgId></xml>"
    )
    enc = encrypt_msg(key, "corpA", inner)
    assert decrypt_msg(key, "corpA", enc) == inner
    event = adapter.parse_inbound(
        {
            "instance_id": "w1",
            "body": {
                "_instance": {
                    "config": {"corp_id": "corpA"},
                    "secrets": {"encoding_aes_key": key_b64},
                },
                "Encrypt": enc,
            },
        }
    )
    assert event.text == "你好"
    assert event.is_group is False

    group_xml = (
        "<xml><FromUserName>user1</FromUserName><ChatId>wr1</ChatId>"
        "<MsgType>text</MsgType><Content>裸消息</Content><MsgId>10</MsgId></xml>"
    )
    group = adapter.parse_inbound(
        {"instance_id": "w1", "body": {"xml": group_xml}}
    )
    assert group.is_group is True
    assert group.mentioned_bot is False


def test_wecom_validate_save_without_public_url():
    adapter = WecomAdapter()
    cfg = {"corp_id": "ww", "agent_id": "1"}
    sec = {
        "corp_secret": "s",
        "token": "t",
        "encoding_aes_key": _aes_key_b64(),
    }
    status, detail = adapter.validate_config(
        cfg, sec, public_base_url=None, enabling=False
    )
    assert status == "disabled"
    assert detail is None
    status, detail = adapter.validate_config(
        cfg, sec, public_base_url=None, enabling=True
    )
    assert status == "error"
    assert "公网根" in (detail or "")
    status, detail = adapter.validate_config(
        cfg, sec, public_base_url="https://example.com", enabling=True
    )
    assert status == "enabled"


def test_wecom_instance_enable_without_public_url(tmp_path):
    app, client = _setup(tmp_path)
    try:
        saved = client.post(
            "/api/channel-plugins/instances",
            json={
                "type_id": "wecom",
                "name": "企微",
                "enabled": False,
                "config": {"corp_id": "ww", "agent_id": "100"},
                "secrets": {
                    "corp_secret": "s",
                    "token": "tok",
                    "encoding_aes_key": _aes_key_b64(),
                },
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["status"] == "disabled"
        enabled = client.post(
            "/api/channel-plugins/instances",
            json={
                "type_id": "wecom",
                "name": "企微启用",
                "enabled": True,
                "config": {"corp_id": "ww", "agent_id": "100"},
                "secrets": {
                    "corp_secret": "s",
                    "token": "tok",
                    "encoding_aes_key": _aes_key_b64(),
                },
            },
        )
        assert enabled.status_code == 200, enabled.text
        body = enabled.json()
        assert body["enabled"] is True
        assert body["status"] == "error"
        assert "公网根" in (body.get("status_detail") or "")
        upcoming = client.post(
            "/api/channel-plugins/instances",
            json={"type_id": "wechat_mp", "name": "公众号"},
        )
        assert upcoming.status_code == 400
        assert "即将支持" in upcoming.text
    finally:
        _close(client)


def test_slack_socket_mode_does_not_need_public_url(tmp_path):
    app, client = _setup(tmp_path)
    try:
        r = client.post(
            "/api/channel-plugins/instances",
            json={
                "type_id": "slack",
                "name": "Slack",
                "config": {"ingress": "websocket"},
                "secrets": {"bot_token": "xoxb-1", "app_token": "xapp-1"},
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "enabled"
        inst = r.json()
        bare = TestClient(app)
        challenge = bare.post(
            f"/api/channels/{inst['id']}/slack",
            json={"type": "url_verification", "challenge": "c-1"},
        )
        assert challenge.status_code == 200, challenge.text
        assert challenge.json()["challenge"] == "c-1"
    finally:
        _close(client)


def test_enqueue_group_mention_and_mapped_thread(tmp_path):
    app, client = _setup(tmp_path)
    try:
        created = client.post(
            "/api/channel-plugins/instances",
            json={
                "type_id": "feishu",
                "name": "飞书群",
                "config": {"app_id": "cli_test", "ingress": "websocket"},
                "secrets": {"app_secret": "plain-secret"},
            },
        )
        assert created.status_code == 200, created.text
        inst = created.json()
        app.state.container.channel_registry.get("feishu").send_outbound = (
            lambda _i, text, **_k: None
        )
        adapter = FeishuAdapter()
        first = adapter.parse_inbound(
            {
                "instance_id": inst["id"],
                "body": _feishu_group(
                    text="@bot 帮我",
                    event_id="mention-1",
                    message_id="om_root",
                    mentions=[{"id": {"open_id": "ou_bot"}}],
                ),
            }
        )
        assert first.mentioned_bot is True
        out = app.state.container.channel_turns.enqueue_now(first)
        assert out["status"] == "accepted"
        _wait_drain(app, inst["id"])
        convs = app.state.container.conversations.list_all(role_id=inst["role_id"])
        assert len(convs) == 1
        cid = convs[0]["id"]

        follow = adapter.parse_inbound(
            {
                "instance_id": inst["id"],
                "body": _feishu_group(
                    text="补充一句",
                    event_id="follow-1",
                    message_id="om_follow",
                    parent_id="om_root",
                ),
            }
        )
        assert follow.mentioned_bot is False
        assert follow.quoted is True
        out2 = app.state.container.channel_turns.enqueue_now(follow)
        assert out2["status"] == "accepted"
        _wait_drain(app, inst["id"])
        convs = app.state.container.conversations.list_all(role_id=inst["role_id"])
        assert len(convs) == 1
        conv = app.state.container.conversations.get(cid)
        user_msgs = [
            m for m in conv.get("messages") or [] if m.get("role") == "user"
        ]
        assert len(user_msgs) >= 2
    finally:
        _close(client)


def test_enqueue_group_bare_reason(tmp_path):
    app, client = _setup(tmp_path)
    try:
        created = client.post(
            "/api/channel-plugins/instances",
            json={
                "type_id": "feishu",
                "name": "飞书群",
                "config": {"app_id": "cli_test", "ingress": "websocket"},
                "secrets": {"app_secret": "plain-secret"},
            },
        )
        inst = created.json()
        event = FeishuAdapter().parse_inbound(
            {"instance_id": inst["id"], "body": _feishu_group()}
        )
        out = app.state.container.channel_turns.enqueue_now(event)
        assert out == {"status": "ignored", "reason": "group_bare"}
    finally:
        _close(client)


def test_wecom_url_verify_echostr():
    adapter = WecomAdapter()
    key_b64 = _aes_key_b64()
    key = decode_aes_key(key_b64)
    echo = encrypt_msg(key, "corpA", "ping-ok")
    token = "tok"
    ts = "1"
    nonce = "n"
    sig = signature(token, ts, nonce, echo)
    inst = {
        "config": {"corp_id": "corpA"},
        "secrets": {"token": token, "encoding_aes_key": key_b64},
    }
    raw = {
        "instance_id": "w1",
        "body": {"_instance": inst},
        "headers": {},
        "query": {
            "timestamp": ts,
            "nonce": nonce,
            "msg_signature": sig,
            "echostr": echo,
        },
    }
    adapter.authenticate(inst, raw)
    challenge = adapter.challenge(raw)
    assert challenge == {"_plaintext": "ping-ok"}


def test_group_sandbox_tools_stripped_when_disabled():
    names = {
        item["function"]["name"]
        for item in select_tools(MODE_API, web_enabled=False, sandbox_enabled=False)
    }
    assert "sandbox_run" not in names
    assert "write_doc" not in names
