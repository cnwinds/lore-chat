"""企业微信应用回调：验签解密 + 发消息。需要公网根。"""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from app.engine.channel_plugins.aes_pkcs7 import (
    decode_aes_key,
    decrypt_msg,
    signature,
)
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

WECOM_TYPE_ID = "wecom"
TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"
MEDIA_URL = "https://qyapi.weixin.qq.com/cgi-bin/media/get"


class WecomAdapter:
    spec = ChannelTypeSpec(
        type_id=WECOM_TYPE_ID,
        display_name="企业微信",
        ingress="http_webhook",
        needs_public_url=True,
        available=True,
        ack_deadline_ms=5000,
        capabilities=frozenset({"async_reply", "group", "media"}),
        config_schema={
            "type": "object",
            "properties": {
                "corp_id": {"type": "string", "title": "企业 ID"},
                "agent_id": {"type": "string", "title": "Agent ID"},
                "callback_url": {
                    "type": "string",
                    "title": "回调 URL",
                    "description": "只读展示",
                },
                "sandbox_allow_senders": {
                    "type": "string",
                    "title": "群聊沙箱白名单",
                },
            },
            "required": ["corp_id", "agent_id"],
        },
        secret_schema={
            "type": "object",
            "properties": {
                "corp_secret": {"type": "string", "title": "Secret"},
                "token": {"type": "string", "title": "Token"},
                "encoding_aes_key": {"type": "string", "title": "EncodingAESKey"},
            },
            "required": ["corp_secret", "token", "encoding_aes_key"],
        },
    )

    def __init__(self, *, http: httpx.Client | None = None):
        self._http = http
        self._owns_http = http is None
        self._token_cache: dict[str, tuple[str, float]] = {}

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
        if not str(cfg.get("corp_id") or "").strip():
            return STATUS_ERROR, "缺少企业 ID"
        if not str(cfg.get("agent_id") or "").strip():
            return STATUS_ERROR, "缺少 Agent ID"
        if not str(sec.get("corp_secret") or "").strip():
            return STATUS_ERROR, "缺少 Secret"
        if not str(sec.get("token") or "").strip():
            return STATUS_ERROR, "缺少 Token"
        if not str(sec.get("encoding_aes_key") or "").strip():
            return STATUS_ERROR, "缺少 EncodingAESKey"
        if enabling and not (public_base_url or "").strip():
            return STATUS_ERROR, missing_public_url_detail()
        if enabling:
            return STATUS_ENABLED, None
        return STATUS_DISABLED, None

    def start(self, instance: dict[str, Any]) -> None:
        del instance

    def stop(self, instance: dict[str, Any]) -> None:
        del instance

    def create_session(self, instance: dict[str, Any], *, on_payload, on_status):
        del instance, on_payload, on_status
        return None

    def authenticate(self, instance: dict[str, Any], raw: Any) -> None:
        _iid, body, _headers, query = unwrap_raw(raw)
        sec = instance.get("secrets") or {}
        token = str(sec.get("token") or "").strip()
        ts = query.get("timestamp") or ""
        nonce = query.get("nonce") or ""
        sig = query.get("msg_signature") or ""
        encrypt = ""
        if query.get("echostr"):
            encrypt = query.get("echostr") or ""
        else:
            xml = _xml_map(_body_xml(body))
            encrypt = xml.get("Encrypt") or ""
        if not token or signature(token, ts, nonce, encrypt) != sig:
            raise ValueError("企业微信签名校验失败")

    def challenge(self, raw: Any) -> Any | None:
        _iid, body, _headers, query = unwrap_raw(raw)
        echo = (query.get("echostr") or "").strip()
        if not echo:
            return None
        instance = body.get("_instance") if isinstance(body.get("_instance"), dict) else {}
        sec = instance.get("secrets") or {}
        cfg = instance.get("config") or {}
        try:
            key = decode_aes_key(str(sec.get("encoding_aes_key") or ""))
            plain = decrypt_msg(key, str(cfg.get("corp_id") or ""), echo)
        except Exception:
            # 验签在 authenticate；这里只解密 echostr
            raise
        return {"_plaintext": plain}

    def parse_inbound(self, raw: Any) -> InboundEvent:
        instance_id, body, _headers, _query = unwrap_raw(raw)
        instance = body.get("_instance") if isinstance(body.get("_instance"), dict) else {}
        xml_text = _body_xml(body)
        fields = _xml_map(xml_text)
        encrypt = fields.get("Encrypt")
        if encrypt:
            sec = instance.get("secrets") or {}
            cfg = instance.get("config") or {}
            key = decode_aes_key(str(sec.get("encoding_aes_key") or ""))
            xml_text = decrypt_msg(key, str(cfg.get("corp_id") or ""), encrypt)
            fields = _xml_map(xml_text)
        msg_type = (fields.get("MsgType") or "text").lower()
        user = fields.get("FromUserName") or None
        chat_id = fields.get("ChatId") or None
        agent = fields.get("AgentID") or fields.get("AgentId") or ""
        is_group = bool(chat_id)
        text = (fields.get("Content") or "").strip()
        mentioned = (not is_group) or ("@" in text) or bool(fields.get("MentionedList"))
        media: list[InboundMedia] = []
        if msg_type in {"image", "voice", "video", "file"}:
            media.append(
                InboundMedia(
                    filename=f"wecom-{msg_type}",
                    kind="image" if msg_type == "image" else "file",
                    file_key=fields.get("MediaId") or fields.get("PicUrl"),
                    url=fields.get("PicUrl") or None,
                )
            )
            if not text:
                text = "[图片]" if msg_type == "image" else "[文件]"
        event_id = fields.get("MsgId") or fields.get("MsgID")
        return InboundEvent(
            instance_id=instance_id,
            text=text if msg_type == "text" or media else "",
            event_id=str(event_id).strip() if event_id else None,
            external_user_id=user,
            display_name=user,
            external_chat_id=chat_id or user,
            media=media,
            is_group=is_group,
            mentioned_bot=mentioned,
            extra={"agent_id": agent},
        )

    def download_media(
        self, instance: dict[str, Any], item: InboundMedia, **kwargs: Any
    ) -> bytes | None:
        if item.data:
            return item.data
        if item.url:
            resp = self._client().get(item.url)
            if resp.status_code == 200:
                return resp.content
        media_id = (item.file_key or "").strip()
        if not media_id:
            return None
        token = self._access_token(instance)
        resp = self._client().get(MEDIA_URL, params={"access_token": token, "media_id": media_id})
        if resp.status_code != 200:
            raise RuntimeError(f"wecom media {resp.status_code}")
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
        cfg = instance.get("config") or {}
        agent_id = str(cfg.get("agent_id") or "").strip()
        token = self._access_token(instance)
        is_group = bool(kwargs.get("is_group"))
        chat_id = str(kwargs.get("chat_id") or kwargs.get("external_chat_id") or "").strip()
        user = str(kwargs.get("open_id") or kwargs.get("external_user_id") or "").strip()
        payload: dict[str, Any] = {
            "msgtype": "text",
            "agentid": int(agent_id) if agent_id.isdigit() else agent_id,
            "text": {"content": body},
        }
        if is_group and chat_id:
            payload["chatid"] = chat_id
        elif user:
            payload["touser"] = user
        else:
            raise ValueError("缺少企业微信接收人")
        resp = self._client().post(SEND_URL, params={"access_token": token}, json=payload)
        data = _json(resp)
        if data.get("errcode") not in (0, None):
            raise RuntimeError(data.get("errmsg") or "wecom send failed")

    def _access_token(self, instance: dict[str, Any]) -> str:
        cfg = instance.get("config") or {}
        sec = instance.get("secrets") or {}
        corp_id = str(cfg.get("corp_id") or "").strip()
        secret = str(sec.get("corp_secret") or "").strip()
        cached = self._token_cache.get(corp_id)
        now = time.time()
        if cached and cached[1] > now + 60:
            return cached[0]
        resp = self._client().get(TOKEN_URL, params={"corpid": corp_id, "corpsecret": secret})
        data = _json(resp)
        token = str(data.get("access_token") or "").strip()
        if not token:
            raise RuntimeError(data.get("errmsg") or "无法获取企微 access_token")
        expire = float(data.get("expires_in") or 7200)
        self._token_cache[corp_id] = (token, now + max(60.0, expire - 60))
        return token


def _body_xml(body: dict[str, Any]) -> str:
    if isinstance(body.get("xml"), str):
        return body["xml"]
    if isinstance(body.get("_raw"), str) and body["_raw"].lstrip().startswith("<"):
        return body["_raw"]
    if isinstance(body.get("Encrypt"), str):
        return (
            f"<xml><Encrypt><![CDATA[{body['Encrypt']}]]></Encrypt></xml>"
        )
    return ""


def _xml_map(xml_text: str) -> dict[str, str]:
    text = (xml_text or "").strip()
    if not text:
        return {}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return {}
    out: dict[str, str] = {}
    for child in root:
        out[child.tag] = (child.text or "").strip()
        if child.tag == "MentionedList":
            items = [item.text or "" for item in child]
            out["MentionedList"] = ",".join(x for x in items if x)
    return out


def _json(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}
