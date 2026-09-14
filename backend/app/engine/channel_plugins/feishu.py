"""飞书通道：默认长连接；私聊文本归一化；出站走开放平台发消息。"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.engine.channel_plugins.group_policy import missing_public_url_detail
from app.engine.channel_plugins.types import (
    STATUS_DISABLED,
    STATUS_ENABLED,
    STATUS_ERROR,
    ChannelTypeSpec,
    InboundEvent,
    InboundMedia,
)

_log = logging.getLogger(__name__)

FEISHU_TYPE_ID = "feishu"
INGRESS_WEBSOCKET = "websocket"
INGRESS_WEBHOOK = "http_webhook"
OPEN_API_BASE = "https://open.feishu.cn"
TOKEN_PATH = "/open-apis/auth/v3/tenant_access_token/internal"
SEND_PATH = "/open-apis/im/v1/messages"


class FeishuAdapter:
    spec = ChannelTypeSpec(
        type_id=FEISHU_TYPE_ID,
        display_name="飞书",
        ingress=INGRESS_WEBSOCKET,
        needs_public_url=False,
        available=True,
        ack_deadline_ms=None,
        capabilities=frozenset({"async_reply", "group", "media", "thread"}),
        config_schema={
            "type": "object",
            "properties": {
                "app_id": {"type": "string", "title": "App ID"},
                "ingress": {
                    "type": "string",
                    "enum": [INGRESS_WEBSOCKET, INGRESS_WEBHOOK],
                    "default": INGRESS_WEBSOCKET,
                    "title": "接入方式",
                },
                "webhook_url": {
                    "type": "string",
                    "title": "Webhook URL",
                    "description": "仅 webhook 模式只读展示",
                },
                "sandbox_allow_senders": {
                    "type": "string",
                    "title": "群聊沙箱白名单",
                    "description": "外部用户 open_id，逗号分隔；空则群聊关沙箱",
                },
            },
            "required": ["app_id"],
        },
        secret_schema={
            "type": "object",
            "properties": {
                "app_secret": {"type": "string", "title": "App Secret"},
                "verification_token": {
                    "type": "string",
                    "title": "Verification Token",
                },
                "encrypt_key": {"type": "string", "title": "Encrypt Key"},
            },
            "required": ["app_secret"],
        },
    )

    def __init__(self, *, http: httpx.Client | None = None):
        self._http = http
        self._owns_http = http is None
        self._token_cache: dict[str, tuple[str, float]] = {}
        self._bot_ids: dict[str, str] = {}

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
        app_id = str(cfg.get("app_id") or "").strip()
        app_secret = str(sec.get("app_secret") or "").strip()
        ingress = str(cfg.get("ingress") or INGRESS_WEBSOCKET).strip() or INGRESS_WEBSOCKET
        if not app_id:
            return STATUS_ERROR, "缺少 App ID"
        if not app_secret:
            return STATUS_ERROR, "缺少 App Secret"
        if ingress == INGRESS_WEBHOOK:
            if enabling and not (public_base_url or "").strip():
                return STATUS_ERROR, missing_public_url_detail()
            if enabling:
                return (
                    STATUS_ERROR,
                    "当前版本请使用长连接；HTTP 回调尚未接入",
                )
            return STATUS_DISABLED, None
        if enabling:
            return STATUS_ENABLED, None
        return STATUS_DISABLED, None

    def start(self, instance: dict[str, Any]) -> None:
        del instance

    def stop(self, instance: dict[str, Any]) -> None:
        del instance

    def create_session(self, instance: dict[str, Any], *, on_payload, on_status):
        from app.engine.channel_plugins.feishu_ws import FeishuWsSession

        cfg = instance.get("config") or {}
        sec = instance.get("secrets") or {}
        if str(cfg.get("ingress") or INGRESS_WEBSOCKET) != INGRESS_WEBSOCKET:
            return None
        app_id = str(cfg.get("app_id") or "").strip()
        app_secret = str(sec.get("app_secret") or "").strip()
        if not app_id or not app_secret:
            return None
        return FeishuWsSession(
            instance_id=instance["id"],
            app_id=app_id,
            app_secret=app_secret,
            on_payload=on_payload,
            on_status=on_status,
            http=self._http,
        )

    def parse_inbound(self, raw: Any) -> InboundEvent:
        instance_id, body = _unwrap(raw)
        header, event = _header_event(body)
        event_type = str(header.get("event_type") or "").strip()
        sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        sender_type = str(sender.get("sender_type") or "").strip() or "user"
        chat_type = str(message.get("chat_type") or "").strip()
        msg_type = str(message.get("message_type") or "").strip()
        is_group = chat_type not in {"p2p", "private"}
        text = ""
        media: list[InboundMedia] = []
        content = message.get("content")
        if (
            event_type in {"", "im.message.receive_v1"}
            and sender_type == "user"
            and msg_type == "text"
        ):
            text = _text_from_content(content)
        elif (
            event_type in {"", "im.message.receive_v1"}
            and sender_type == "user"
            and msg_type in {"image", "file", "audio", "media"}
        ):
            parsed = content
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    parsed = {}
            if isinstance(parsed, dict):
                key = str(
                    parsed.get("image_key")
                    or parsed.get("file_key")
                    or ""
                ).strip()
                media.append(
                    InboundMedia(
                        filename=str(parsed.get("file_name") or f"feishu-{msg_type}"),
                        kind="image" if msg_type == "image" else "file",
                        file_key=key or None,
                    )
                )
            text = "[图片]" if msg_type == "image" else "[文件]"
        sender_id = sender.get("sender_id") if isinstance(sender.get("sender_id"), dict) else {}
        open_id = str(
            sender_id.get("open_id")
            or sender.get("open_id")
            or ""
        ).strip() or None
        chat_id = str(message.get("chat_id") or "").strip() or None
        message_id = str(message.get("message_id") or "").strip() or None
        event_id = str(
            header.get("event_id") or message_id or ""
        ).strip() or None
        thread_id = str(message.get("thread_id") or "").strip() or None
        parent_id = str(message.get("parent_id") or "").strip() or None
        root_id = str(message.get("root_id") or "").strip() or None
        quoted = bool(parent_id or root_id)
        mentioned = _mentions_bot(message.get("mentions"), self._bot_ids.get(instance_id))
        if not thread_id:
            thread_id = root_id or parent_id
        if is_group and mentioned and not thread_id:
            thread_id = message_id
        return InboundEvent(
            instance_id=instance_id,
            text=text,
            event_id=event_id,
            external_user_id=open_id,
            display_name=open_id,
            external_chat_id=chat_id,
            external_thread_id=thread_id,
            reply_to_id=message_id,
            media=media,
            is_group=is_group,
            mentioned_bot=mentioned,
            quoted=quoted,
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
        chat_id = str(
            kwargs.get("chat_id")
            or kwargs.get("external_chat_id")
            or ""
        ).strip()
        open_id = str(
            kwargs.get("open_id") or kwargs.get("external_user_id") or ""
        ).strip()
        if chat_id:
            receive_id, receive_id_type = chat_id, "chat_id"
        elif open_id:
            receive_id, receive_id_type = open_id, "open_id"
        else:
            raise ValueError("缺少 chat_id，无法写出站")
        secrets = instance.get("secrets") or {}
        config = instance.get("config") or {}
        app_id = str(config.get("app_id") or "").strip()
        app_secret = str(secrets.get("app_secret") or "").strip()
        if not app_id or not app_secret:
            raise ValueError("缺少 App ID / App Secret")
        token = self._tenant_token(app_id, app_secret)
        payload = {
            "msg_type": "text",
            "content": json.dumps({"text": body}, ensure_ascii=False),
        }
        reply_to = str(kwargs.get("reply_to_id") or "").strip()
        thread_id = str(
            kwargs.get("thread_id") or kwargs.get("external_thread_id") or ""
        ).strip()
        headers = {"Authorization": f"Bearer {token}"}
        if reply_to and (kwargs.get("is_group") or thread_id):
            resp = self._client().post(
                f"{OPEN_API_BASE}{SEND_PATH}/{reply_to}/reply",
                headers=headers,
                json=payload,
            )
        else:
            payload["receive_id"] = receive_id
            resp = self._client().post(
                f"{OPEN_API_BASE}{SEND_PATH}",
                params={"receive_id_type": receive_id_type},
                headers=headers,
                json=payload,
            )
        data = _json_body(resp)
        code = data.get("code")
        if resp.status_code == 200 and code in (0, None):
            return
        raise RuntimeError(data.get("msg") or f"feishu send failed: {resp.status_code}")

    def download_media(self, instance: dict[str, Any], item: InboundMedia, **kwargs) -> bytes | None:
        file_key = (item.file_key or "").strip()
        if not file_key:
            return None
        event = kwargs.get("event")
        message_id = str(getattr(event, "reply_to_id", "") or "").strip()
        secrets = instance.get("secrets") or {}
        config = instance.get("config") or {}
        token = self._tenant_token(
            str(config.get("app_id") or "").strip(),
            str(secrets.get("app_secret") or "").strip(),
        )
        if not message_id:
            resp = self._client().get(
                f"{OPEN_API_BASE}/open-apis/image/v4/get",
                params={"image_key": file_key},
                headers={"Authorization": f"Bearer {token}"},
            )
        else:
            kind = "image" if item.kind == "image" else "file"
            resp = self._client().get(
                f"{OPEN_API_BASE}{SEND_PATH}/{message_id}/resources/{file_key}",
                params={"type": kind},
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code != 200:
            raise RuntimeError(f"feishu media {resp.status_code}")
        return resp.content

    def challenge(self, raw: Any) -> Any | None:
        from app.engine.channel_plugins.rawutil import unwrap_raw

        if isinstance(raw, dict) and raw.get("type") == "url_verification":
            return {"challenge": raw.get("challenge")}
        _iid, body, _headers, _query = unwrap_raw(raw)
        if body.get("type") == "url_verification":
            return {"challenge": body.get("challenge")}
        return None

    def _tenant_token(self, app_id: str, app_secret: str) -> str:
        cached = self._token_cache.get(app_id)
        now = time.time()
        if cached and cached[1] > now + 60:
            return cached[0]
        resp = self._client().post(
            f"{OPEN_API_BASE}{TOKEN_PATH}",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        data = _json_body(resp)
        token = str(data.get("tenant_access_token") or "").strip()
        if not token:
            raise RuntimeError(data.get("msg") or "无法获取飞书 tenant_access_token")
        expire = float(data.get("expire") or 7200)
        self._token_cache[app_id] = (token, now + max(60.0, expire - 60))
        return token


def _unwrap(raw: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(raw, tuple) and len(raw) == 2:
        return str(raw[0] or ""), _as_dict(raw[1])
    if isinstance(raw, dict) and "body" in raw and "instance_id" in raw:
        return str(raw.get("instance_id") or ""), _as_dict(raw.get("body"))
    data = _as_dict(raw)
    return str(data.get("instance_id") or ""), data


def _as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    header = getattr(raw, "header", None)
    event = getattr(raw, "event", None)
    if header is None and event is None:
        return {}
    return {"header": _obj_dict(header), "event": _obj_dict(event)}


def _obj_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return {}


def _header_event(body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    header = body.get("header") if isinstance(body.get("header"), dict) else {}
    event = body.get("event") if isinstance(body.get("event"), dict) else body
    if not header and isinstance(body.get("schema"), str):
        header = {
            "event_id": body.get("event_id"),
            "event_type": body.get("event_type") or body.get("type"),
        }
    return header, event if isinstance(event, dict) else {}


def _mentions_bot(mentions: Any, bot_open_id: str | None) -> bool:
    if not mentions:
        return False
    if not isinstance(mentions, list):
        return True
    if not bot_open_id:
        return True
    for item in mentions:
        if not isinstance(item, dict):
            continue
        ident = item.get("id") if isinstance(item.get("id"), dict) else item
        oid = str(
            (ident or {}).get("open_id")
            or item.get("open_id")
            or ""
        ).strip()
        if oid and oid == bot_open_id:
            return True
    return False


def _text_from_content(content: Any) -> str:
    if isinstance(content, dict):
        return str(content.get("text") or "").strip()
    if not isinstance(content, str):
        return ""
    raw = content.strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(parsed, dict):
        return str(parsed.get("text") or "").strip()
    return raw


def _json_body(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}
