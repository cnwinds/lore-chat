"""Slack Socket Mode：apps.connections.open + JSON envelope ACK。"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Callable
from typing import Any

import httpx

from app.engine.channel_plugins.rawutil import default_ws_connect
from app.engine.channel_plugins.types import STATUS_ENABLED, STATUS_ERROR

_log = logging.getLogger(__name__)

OPEN_URL = "https://slack.com/api/apps.connections.open"
StatusCb = Callable[[str, str | None], None]
PayloadCb = Callable[[dict[str, Any]], None]


class SlackAuthError(RuntimeError):
    pass


class SlackSocketSession:
    def __init__(
        self,
        *,
        instance_id: str,
        app_token: str,
        on_payload: PayloadCb,
        on_status: StatusCb,
        http: httpx.Client | None = None,
        connect=None,
    ):
        self.instance_id = instance_id
        self._app_token = app_token
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
                self._run(), name=f"slack-ws-{self.instance_id}"
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
            except SlackAuthError as e:
                _log.warning("slack socket auth failed instance=%s err=%s", self.instance_id, e)
                self._on_status(STATUS_ERROR, str(e))
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _log.warning("slack socket dropped instance=%s err=%s", self.instance_id, e)
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
                headers={"Authorization": f"Bearer {self._app_token}"},
            )
            data = resp.json() if resp.content else {}
            if not isinstance(data, dict):
                data = {}
            if resp.status_code in {401, 403} or data.get("error") in {
                "invalid_auth",
                "not_authed",
                "token_revoked",
            }:
                raise SlackAuthError(data.get("error") or "Slack 鉴权失败")
            if not data.get("ok"):
                raise RuntimeError(data.get("error") or f"获取 Socket Mode URL 失败 HTTP {resp.status_code}")
            url = str(data.get("url") or "").strip()
            if not url:
                raise RuntimeError("Slack 未返回 Socket Mode URL")
            return url
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
                    envelope = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(envelope, dict):
                    continue
                etype = str(envelope.get("type") or "")
                if etype == "hello":
                    continue
                envelope_id = envelope.get("envelope_id")
                if envelope_id:
                    try:
                        await ws.send(json.dumps({"envelope_id": envelope_id}))
                    except Exception:
                        _log.exception("slack ack failed instance=%s", self.instance_id)
                if etype in {"events_api", "event_callback"} or envelope.get("payload"):
                    try:
                        self._on_payload({"instance_id": self.instance_id, "body": envelope})
                    except Exception:
                        _log.exception("slack inbound handler failed instance=%s", self.instance_id)
        finally:
            self._ws = None
            try:
                await ws.close()
            except Exception:
                pass
