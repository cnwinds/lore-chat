"""钉钉 Stream：注册 ticket 后 WebSocket 收 CALLBACK/SYSTEM 并 ACK。"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import httpx

from app.engine.channel_plugins.aes_pkcs7 import local_ip
from app.engine.channel_plugins.rawutil import default_ws_connect
from app.engine.channel_plugins.types import STATUS_ENABLED, STATUS_ERROR

_log = logging.getLogger(__name__)

OPEN_URL = "https://api.dingtalk.com/v1.0/gateway/connections/open"
BOT_TOPIC = "/v1.0/im/bot/messages/get"
StatusCb = Callable[[str, str | None], None]
PayloadCb = Callable[[dict[str, Any]], None]


class DingTalkAuthError(RuntimeError):
    pass


class DingTalkStreamSession:
    def __init__(
        self,
        *,
        instance_id: str,
        app_key: str,
        app_secret: str,
        on_payload: PayloadCb,
        on_status: StatusCb,
        http: httpx.Client | None = None,
        connect=None,
    ):
        self.instance_id = instance_id
        self._app_key = app_key
        self._app_secret = app_secret
        self._on_payload = on_payload
        self._on_status = on_status
        self._http = http
        self._connect = connect
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._ws = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._task is None or self._task.done():
            self._stop = asyncio.Event()
            self._task = loop.create_task(
                self._run(), name=f"dingtalk-ws-{self.instance_id}"
            )

    async def astop(self) -> None:
        self._stop.set()
        ws = self._ws
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None

    async def _run(self) -> None:
        delay = 1.0
        while not self._stop.is_set():
            try:
                url = await asyncio.to_thread(self._discover)
                delay = 1.0
                self._on_status(STATUS_ENABLED, None)
                await self._pump(url)
            except DingTalkAuthError as e:
                _log.warning("dingtalk stream auth failed instance=%s err=%s", self.instance_id, e)
                self._on_status(STATUS_ERROR, str(e))
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _log.warning("dingtalk stream dropped instance=%s err=%s", self.instance_id, e)
                self._on_status(STATUS_ERROR, f"长连接断开，正在重连：{e}")
            if self._stop.is_set():
                return
            jitter = random.random() * min(3.0, delay)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay + jitter)
                return
            except asyncio.TimeoutError:
                delay = min(delay * 2, 120.0)

    def _discover(self) -> str:
        client = self._http or httpx.Client(timeout=20.0)
        owns = self._http is None
        try:
            resp = client.post(
                OPEN_URL,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "lore-chat-dingtalk-stream/1",
                },
                json={
                    "clientId": self._app_key,
                    "clientSecret": self._app_secret,
                    "subscriptions": [{"type": "CALLBACK", "topic": BOT_TOPIC}],
                    "ua": "lore-chat-dingtalk-stream/1",
                    "localIp": local_ip(),
                },
            )
            data = resp.json() if resp.content else {}
            if not isinstance(data, dict):
                data = {}
            if resp.status_code in {401, 403}:
                raise DingTalkAuthError(data.get("message") or "钉钉鉴权失败")
            if resp.status_code != 200:
                raise RuntimeError(data.get("message") or f"获取 Stream 失败 HTTP {resp.status_code}")
            endpoint = str(data.get("endpoint") or "").strip()
            ticket = str(data.get("ticket") or "").strip()
            if not endpoint or not ticket:
                raise RuntimeError("钉钉未返回 Stream endpoint")
            parsed = urlparse(endpoint)
            query = f"ticket={quote(ticket)}"
            if parsed.query:
                query = f"{parsed.query}&{query}"
            return urlunparse(parsed._replace(query=query))
        finally:
            if owns:
                client.close()

    async def _pump(self, url: str) -> None:
        connect = self._connect or default_ws_connect
        ws = await connect(url)
        self._ws = ws
        try:
            while not self._stop.is_set():
                raw = await ws.recv()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                headers = message.get("headers") if isinstance(message.get("headers"), dict) else {}
                msg_id = str(headers.get("messageId") or "")
                mtype = str(message.get("type") or "").upper()
                topic = str(headers.get("topic") or "")
                ack_data = '{"response": null}'
                if mtype == "SYSTEM" and topic == "ping":
                    ack_data = message.get("data") if isinstance(message.get("data"), str) else json.dumps(
                        {"opaque": None}, ensure_ascii=False
                    )
                    if isinstance(message.get("data"), str):
                        ack_data = message["data"]
                elif mtype == "EVENT":
                    ack_data = json.dumps({"status": "SUCCESS", "message": "success"})
                if mtype == "SYSTEM" and topic == "disconnect":
                    self._stop.set()
                    continue
                if msg_id:
                    ack = {
                        "code": 200,
                        "message": "OK",
                        "headers": {
                            "contentType": "application/json",
                            "messageId": msg_id,
                        },
                        "data": ack_data,
                    }
                    try:
                        await ws.send(json.dumps(ack))
                    except Exception:
                        _log.exception("dingtalk ack failed instance=%s", self.instance_id)
                if mtype == "CALLBACK":
                    try:
                        self._on_payload({"instance_id": self.instance_id, "body": message})
                    except Exception:
                        _log.exception("dingtalk inbound handler failed instance=%s", self.instance_id)
        finally:
            self._ws = None
            try:
                await ws.close()
            except Exception:
                pass
