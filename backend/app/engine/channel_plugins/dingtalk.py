"""钉钉通道：默认 Stream 长连接。"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.engine.channel_plugins.group_policy import missing_public_url_detail
from app.engine.channel_plugins.rawutil import unwrap_raw
from app.engine.channel_plugins.types import (
    STATUS_DISABLED,
    STATUS_ENABLED,
    STATUS_ERROR,
    ChannelTypeSpec,
    InboundEvent,
    InboundMedia,
)

_log = logging.getLogger(__name__)

DINGTALK_TYPE_ID = "dingtalk"
INGRESS_STREAM = "websocket"
INGRESS_WEBHOOK = "http_webhook"


class DingtalkAdapter:
    spec = ChannelTypeSpec(
        type_id=DINGTALK_TYPE_ID,
        display_name="钉钉",
        ingress=INGRESS_STREAM,
        needs_public_url=False,
        available=True,
        ack_deadline_ms=None,
        capabilities=frozenset({"async_reply", "group", "media"}),
        config_schema={
            "type": "object",
            "properties": {
                "app_key": {"type": "string", "title": "AppKey"},
                "robot_code": {"type": "string", "title": "RobotCode"},
                "ingress": {
                    "type": "string",
                    "enum": [INGRESS_STREAM, INGRESS_WEBHOOK],
                    "default": INGRESS_STREAM,
                    "title": "接入方式",
                },
                "sandbox_allow_senders": {
                    "type": "string",
                    "title": "群聊沙箱白名单",
                },
            },
            "required": ["app_key"],
        },
        secret_schema={
            "type": "object",
            "properties": {
                "app_secret": {"type": "string", "title": "AppSecret"},
                "token": {"type": "string", "title": "Token（仅 HTTP 回调）"},
                "aes_key": {"type": "string", "title": "AES Key（仅 HTTP 回调）"},
            },
            "required": ["app_secret"],
        },
    )

    def __init__(self, *, http: httpx.Client | None = None):
        self._http = http
        self._owns_http = http is None

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
        cfg = config or {}
        sec = secrets or {}
        if not str(cfg.get("app_key") or "").strip():
            return STATUS_ERROR, "缺少 AppKey"
        if not str(sec.get("app_secret") or "").strip():
            return STATUS_ERROR, "缺少 AppSecret"
        ingress = str(cfg.get("ingress") or INGRESS_STREAM).strip() or INGRESS_STREAM
        if ingress == INGRESS_WEBHOOK:
            if enabling and not (public_base_url or "").strip():
                return STATUS_ERROR, missing_public_url_detail()
            if enabling:
                return STATUS_ERROR, "当前版本请使用 Stream 长连接；HTTP 回调尚未接入"
            return STATUS_DISABLED, None
        if enabling:
            return STATUS_ENABLED, None
        return STATUS_DISABLED, None

    def start(self, instance: dict[str, Any]) -> None:
        del instance

    def stop(self, instance: dict[str, Any]) -> None:
        del instance

    def create_session(self, instance: dict[str, Any], *, on_payload, on_status):
        from app.engine.channel_plugins.dingtalk_ws import DingTalkStreamSession

        cfg = instance.get("config") or {}
        sec = instance.get("secrets") or {}
        if str(cfg.get("ingress") or INGRESS_STREAM) != INGRESS_STREAM:
            return None
        app_key = str(cfg.get("app_key") or "").strip()
        app_secret = str(sec.get("app_secret") or "").strip()
        if not app_key or not app_secret:
            return None
        return DingTalkStreamSession(
            instance_id=instance["id"],
            app_key=app_key,
            app_secret=app_secret,
            on_payload=on_payload,
            on_status=on_status,
            http=self._http,
        )

    def challenge(self, raw: Any) -> Any | None:
        del raw
        return None

    def parse_inbound(self, raw: Any) -> InboundEvent:
        instance_id, body, _headers, _query = unwrap_raw(raw)
        data = body.get("data") if isinstance(body.get("data"), (dict, str)) else body
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                data = parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                data = {}
        if not isinstance(data, dict):
            data = {}
        headers = body.get("headers") if isinstance(body.get("headers"), dict) else {}
        conv_type = str(data.get("conversationType") or "").strip()
        is_group = conv_type == "2"
        text_obj = data.get("text") if isinstance(data.get("text"), dict) else {}
        text = str(text_obj.get("content") or data.get("content") or "").strip()
        msg_type = str(data.get("msgtype") or data.get("msgType") or "text").strip()
        media: list[InboundMedia] = []
        content = data.get("content") if isinstance(data.get("content"), dict) else {}
        if msg_type in {"picture", "photo", "image"}:
            media.append(
                InboundMedia(
                    filename="dingtalk-image.jpg",
                    kind="image",
                    url=str(content.get("downloadCode") or content.get("picDownloadCode") or "")
                    or None,
                )
            )
            if not text:
                text = "[图片]"
        mentioned = (not is_group) or bool(data.get("isInAtList"))
        at_users = data.get("atUsers")
        if is_group and isinstance(at_users, list) and at_users:
            mentioned = True
        sender = str(
            data.get("senderStaffId") or data.get("senderId") or ""
        ).strip() or None
        chat = str(data.get("conversationId") or "").strip() or None
        event_id = str(
            data.get("msgId")
            or headers.get("messageId")
            or body.get("event_id")
            or ""
        ).strip() or None
        webhook = str(data.get("sessionWebhook") or "").strip() or None
        return InboundEvent(
            instance_id=instance_id,
            text=text,
            event_id=event_id,
            external_user_id=sender,
            display_name=str(data.get("senderNick") or sender or "").strip() or sender,
            external_chat_id=chat,
            media=media,
            is_group=is_group,
            mentioned_bot=mentioned,
            extra={"session_webhook": webhook} if webhook else {},
        )

    def send_outbound(
        self,
        instance: dict[str, Any],
        text: str,
        **kwargs: Any,
    ) -> None:
        body = (text or "").strip()
        if not body:
            return
        webhook = str(
            kwargs.get("session_webhook")
            or ((kwargs.get("extra") or {}).get("session_webhook") if isinstance(kwargs.get("extra"), dict) else "")
            or ""
        ).strip()
        if not webhook:
            raise ValueError("缺少钉钉 sessionWebhook，无法写出站")
        resp = self._client().post(
            webhook,
            json={"msgtype": "text", "text": {"content": body}},
        )
        data = {}
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400 or (
            isinstance(data, dict) and data.get("errcode") not in (0, None)
        ):
            raise RuntimeError(
                (data or {}).get("errmsg") if isinstance(data, dict) else None
                or f"dingtalk send failed: {resp.status_code}"
            )
