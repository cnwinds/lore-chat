"""Slack 通道：默认 Socket Mode；可选 Events API webhook。"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

import httpx

from app.engine.channel_plugins.group_policy import missing_public_url_detail
from app.engine.channel_plugins.rawutil import header_get, unwrap_raw
from app.engine.channel_plugins.types import (
    STATUS_DISABLED,
    STATUS_ENABLED,
    STATUS_ERROR,
    ChannelTypeSpec,
    InboundEvent,
    InboundMedia,
)

_log = logging.getLogger(__name__)

SLACK_TYPE_ID = "slack"
INGRESS_SOCKET = "websocket"
INGRESS_WEBHOOK = "http_webhook"
API_BASE = "https://slack.com/api"


class SlackAdapter:
    spec = ChannelTypeSpec(
        type_id=SLACK_TYPE_ID,
        display_name="Slack",
        ingress=INGRESS_SOCKET,
        needs_public_url=False,
        available=True,
        ack_deadline_ms=3000,
        capabilities=frozenset({"async_reply", "thread", "group", "media"}),
        config_schema={
            "type": "object",
            "properties": {
                "ingress": {
                    "type": "string",
                    "enum": [INGRESS_SOCKET, INGRESS_WEBHOOK],
                    "default": INGRESS_SOCKET,
                    "title": "接入方式",
                },
                "request_url": {
                    "type": "string",
                    "title": "Request URL",
                    "description": "仅 webhook 模式只读展示",
                },
                "sandbox_allow_senders": {
                    "type": "string",
                    "title": "群聊沙箱白名单",
                    "description": "外部用户 id，逗号分隔；空则群聊关沙箱",
                },
            },
        },
        secret_schema={
            "type": "object",
            "properties": {
                "bot_token": {"type": "string", "title": "Bot Token (xoxb-)"},
                "signing_secret": {"type": "string", "title": "Signing Secret"},
                "app_token": {
                    "type": "string",
                    "title": "App Token (xapp-)",
                    "description": "Socket Mode 必填",
                },
            },
            "required": ["bot_token"],
        },
    )

    def __init__(self, *, http: httpx.Client | None = None):
        self._http = http
        self._owns_http = http is None
        self._bot_user: dict[str, str] = {}

    def _client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=20.0)
        return self._http

    def close(self) -> None:
        if self._owns_http and self._http is not None:
            self._http.close()
            self._http = None

    def validate_config(
        self,
        config: dict[str, Any],
        secrets: dict[str, Any],
        *,
        public_base_url: str | None = None,
        enabling: bool = False,
    ) -> tuple[str, str | None]:
        sec = secrets or {}
        cfg = config or {}
        bot = str(sec.get("bot_token") or "").strip()
        ingress = str(cfg.get("ingress") or INGRESS_SOCKET).strip() or INGRESS_SOCKET
        if not bot:
            return STATUS_ERROR, "缺少 Bot Token"
        if ingress == INGRESS_WEBHOOK:
            if enabling and not (public_base_url or "").strip():
                return STATUS_ERROR, missing_public_url_detail()
            if enabling and not str(sec.get("signing_secret") or "").strip():
                return STATUS_ERROR, "webhook 模式需要 Signing Secret"
            if enabling:
                return STATUS_ENABLED, None
            return STATUS_DISABLED, None
        if enabling and not str(sec.get("app_token") or "").strip():
            return STATUS_ERROR, "Socket Mode 需要 App Token (xapp-)"
        if enabling:
            return STATUS_ENABLED, None
        return STATUS_DISABLED, None

    def start(self, instance: dict[str, Any]) -> None:
        del instance

    def stop(self, instance: dict[str, Any]) -> None:
        del instance

    def create_session(self, instance: dict[str, Any], *, on_payload, on_status):
        from app.engine.channel_plugins.slack_ws import SlackSocketSession

        cfg = instance.get("config") or {}
        sec = instance.get("secrets") or {}
        if str(cfg.get("ingress") or INGRESS_SOCKET) != INGRESS_SOCKET:
            return None
        app_token = str(sec.get("app_token") or "").strip()
        if not app_token:
            return None
        return SlackSocketSession(
            instance_id=instance["id"],
            app_token=app_token,
            on_payload=on_payload,
            on_status=on_status,
            http=self._http,
        )

    def authenticate(self, instance: dict[str, Any], raw: Any) -> None:
        cfg = instance.get("config") or {}
        if str(cfg.get("ingress") or INGRESS_SOCKET) != INGRESS_WEBHOOK:
            return
        _instance_id, body, headers, _query = unwrap_raw(raw)
        secret = str((instance.get("secrets") or {}).get("signing_secret") or "").strip()
        if not secret:
            raise ValueError("缺少 Signing Secret")
        ts = header_get(headers, "X-Slack-Request-Timestamp")
        sig = header_get(headers, "X-Slack-Signature")
        raw_body = body.get("_raw") if isinstance(body.get("_raw"), str) else None
        if raw_body is None:
            raw_body = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        if not _valid_slack_sig(secret, ts, raw_body, sig):
            raise ValueError("Slack 签名校验失败")

    def challenge(self, raw: Any) -> Any | None:
        _iid, body, _headers, _query = unwrap_raw(raw)
        if body.get("type") == "url_verification":
            return {"challenge": body.get("challenge")}
        payload = body.get("payload") if isinstance(body.get("payload"), dict) else None
        if payload and payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge")}
        return None

    def parse_inbound(self, raw: Any) -> InboundEvent:
        instance_id, body, _headers, _query = unwrap_raw(raw)
        envelope = body
        if body.get("type") == "events_api" and isinstance(body.get("payload"), dict):
            body = body["payload"]
        event = body.get("event") if isinstance(body.get("event"), dict) else {}
        if not event and body.get("type") in {"message", "app_mention"}:
            event = body
        event_id = str(
            body.get("event_id")
            or envelope.get("envelope_id")
            or event.get("client_msg_id")
            or event.get("event_ts")
            or event.get("ts")
            or ""
        ).strip() or None
        subtype = str(event.get("subtype") or "").strip()
        user = str(event.get("user") or "").strip() or None
        channel = str(event.get("channel") or "").strip() or None
        ts = str(event.get("ts") or "").strip() or None
        thread_ts = str(event.get("thread_ts") or "").strip() or None
        text = str(event.get("text") or "").strip()
        channel_type = str(event.get("channel_type") or "").strip()
        ev_type = str(event.get("type") or body.get("event_type") or "").strip()
        is_group = channel_type != "im"
        if subtype in {"bot_message", "message_changed", "message_deleted"}:
            text = ""
        bot_id = self._bot_user.get(instance_id)
        mentioned = ev_type == "app_mention"
        if bot_id and f"<@{bot_id}>" in text:
            mentioned = True
        # 任意 thread 回复不算「引用机器人」。未 @ 的频道消息忽略；
        # 已映射 thread 由 ChannelTurnService.has_mapped_thread 续聊。
        quoted = False
        reply_thread = thread_ts or (ts if is_group and mentioned else None)
        media: list[InboundMedia] = []
        for fobj in event.get("files") or []:
            if not isinstance(fobj, dict):
                continue
            media.append(
                InboundMedia(
                    filename=str(fobj.get("name") or "slack-file"),
                    kind="image" if str(fobj.get("mimetype") or "").startswith("image/") else "file",
                    mime=fobj.get("mimetype"),
                    url=str(fobj.get("url_private") or fobj.get("url_private_download") or "")
                    or None,
                    file_key=str(fobj.get("id") or "") or None,
                )
            )
        if not text and media:
            text = "[图片]" if media[0].kind == "image" else "[文件]"
        return InboundEvent(
            instance_id=instance_id,
            text=text,
            event_id=event_id,
            external_user_id=user,
            display_name=user,
            external_chat_id=channel,
            external_thread_id=reply_thread,
            reply_to_id=ts,
            media=media,
            is_group=is_group,
            mentioned_bot=mentioned,
            quoted=quoted,
        )

    def download_media(
        self, instance: dict[str, Any], item: InboundMedia, **kwargs: Any
    ) -> bytes | None:
        url = (item.url or "").strip()
        if not url:
            return None
        token = str((instance.get("secrets") or {}).get("bot_token") or "").strip()
        resp = self._client().get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code != 200:
            raise RuntimeError(f"slack file download {resp.status_code}")
        return resp.content

    def send_outbound(
        self,
        instance: dict[str, Any],
        text: str,
        **kwargs: Any,
    ) -> None:
        body = (text or "").strip()
        if not body:
            return
        token = str((instance.get("secrets") or {}).get("bot_token") or "").strip()
        channel = str(
            kwargs.get("chat_id")
            or kwargs.get("external_chat_id")
            or ""
        ).strip()
        if not token or not channel:
            raise ValueError("缺少 Slack Bot Token 或 channel")
        payload: dict[str, Any] = {"channel": channel, "text": body}
        thread = str(
            kwargs.get("thread_id")
            or kwargs.get("external_thread_id")
            or kwargs.get("reply_to_id")
            or ""
        ).strip()
        if thread:
            payload["thread_ts"] = thread
        resp = self._client().post(
            f"{API_BASE}/chat.postMessage",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        data = _json(resp)
        if not data.get("ok"):
            raise RuntimeError(data.get("error") or f"slack send failed: {resp.status_code}")

    def remember_bot_user(self, instance_id: str, user_id: str) -> None:
        if user_id:
            self._bot_user[instance_id] = user_id


def _valid_slack_sig(secret: str, timestamp: str, raw_body: str, signature: str) -> bool:
    if not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(int(time.time()) - ts) > 60 * 5:
        return False
    digest = hmac.new(
        secret.encode("utf-8"),
        f"v0:{timestamp}:{raw_body}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    expected = f"v0={digest}"
    return hmac.compare_digest(expected, signature)


def _json(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}
