"""飞书长连接：在 FastAPI 事件循环上跑，不调用 lark.ws.Client.start()。"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Callable
from typing import Any

import httpx

from app.engine.channel_plugins.feishu_frame import (
    FRAME_CONTROL,
    FRAME_DATA,
    HEADER_MESSAGE_ID,
    HEADER_SEQ,
    HEADER_SUM,
    HEADER_TYPE,
    TYPE_EVENT,
    TYPE_PING,
    TYPE_PONG,
    WsFrame,
    ping_frame,
)
from app.engine.channel_plugins.types import STATUS_ENABLED, STATUS_ERROR

_log = logging.getLogger(__name__)

GEN_ENDPOINT = "https://open.feishu.cn/callback/ws/endpoint"
StatusCb = Callable[[str, str | None], None]
PayloadCb = Callable[[dict[str, Any]], None]


class FeishuAuthError(RuntimeError):
    pass


class FeishuWsSession:
    def __init__(
        self,
        *,
        instance_id: str,
        app_id: str,
        app_secret: str,
        on_payload: PayloadCb,
        on_status: StatusCb,
        http: httpx.Client | None = None,
        connect=None,
    ):
        self.instance_id = instance_id
        self._app_id = app_id
        self._app_secret = app_secret
        self._on_payload = on_payload
        self._on_status = on_status
        self._http = http
        self._connect = connect
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._ws = None
        self._fragments: dict[str, list[bytes | None]] = {}

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._task is None or self._task.done():
            self._stop = asyncio.Event()
            self._task = loop.create_task(self._run(), name=f"feishu-ws-{self.instance_id}")

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
                url, ping_interval = await asyncio.to_thread(self._discover)
                delay = 1.0
                self._on_status(STATUS_ENABLED, None)
                await self._pump(url, ping_interval)
            except FeishuAuthError as e:
                _log.warning("feishu ws auth failed instance=%s err=%s", self.instance_id, e)
                self._on_status(STATUS_ERROR, str(e))
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _log.warning("feishu ws dropped instance=%s err=%s", self.instance_id, e)
                self._on_status(STATUS_ERROR, f"长连接断开，正在重连：{e}")
            if self._stop.is_set():
                return
            jitter = random.random() * min(3.0, delay)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay + jitter)
                return
            except asyncio.TimeoutError:
                delay = min(delay * 2, 120.0)

    def _discover(self) -> tuple[str, int]:
        client = self._http or httpx.Client(timeout=20.0)
        owns = self._http is None
        try:
            resp = client.post(
                GEN_ENDPOINT,
                headers={"locale": "zh", "User-Agent": "lore-chat-feishu-ws/1"},
                json={"AppID": self._app_id, "AppSecret": self._app_secret},
            )
            data = resp.json() if resp.content else {}
            if not isinstance(data, dict):
                data = {}
            code = data.get("code")
            if resp.status_code in {401, 403} or code in {403, 514}:
                raise FeishuAuthError(data.get("msg") or "飞书鉴权失败")
            if resp.status_code != 200 or code not in (0, None):
                raise RuntimeError(data.get("msg") or f"获取长连接失败 HTTP {resp.status_code}")
            payload = data.get("data") if isinstance(data.get("data"), dict) else {}
            url = str(payload.get("URL") or payload.get("url") or "").strip()
            if not url:
                raise RuntimeError("飞书未返回长连接 URL")
            conf = payload.get("ClientConfig") if isinstance(payload.get("ClientConfig"), dict) else {}
            ping = int(conf.get("PingInterval") or 120)
            return url, max(15, ping)
        finally:
            if owns:
                client.close()

    async def _pump(self, url: str, ping_interval: int) -> None:
        connect = self._connect or _default_connect
        ws = await connect(url)
        self._ws = ws
        ping_task = asyncio.create_task(self._ping_loop(ws, ping_interval))
        try:
            while not self._stop.is_set():
                raw = await ws.recv()
                if isinstance(raw, str):
                    raw = raw.encode("utf-8")
                await self._handle_bytes(ws, raw)
        finally:
            ping_task.cancel()
            try:
                await ping_task
            except (asyncio.CancelledError, Exception):
                pass
            self._ws = None
            try:
                await ws.close()
            except Exception:
                pass

    async def _ping_loop(self, ws, ping_interval: int) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.sleep(ping_interval)
                await ws.send(ping_frame(0).encode())
            except asyncio.CancelledError:
                raise
            except Exception:
                return

    async def _handle_bytes(self, ws, raw: bytes) -> None:
        try:
            frame = WsFrame.decode(raw)
        except Exception:
            _log.exception("feishu frame decode failed instance=%s", self.instance_id)
            return
        msg_type = (frame.header(HEADER_TYPE) or "").lower()
        if frame.method == FRAME_CONTROL:
            if msg_type == TYPE_PONG:
                return
            return
        if frame.method != FRAME_DATA:
            return
        payload = self._combine(frame)
        if payload is None:
            return
        if msg_type == TYPE_EVENT:
            try:
                body = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                body = {}
            if isinstance(body, dict):
                try:
                    self._on_payload(body)
                except Exception:
                    _log.exception("feishu inbound handler failed instance=%s", self.instance_id)
            ack = WsFrame(
                seq_id=frame.seq_id,
                log_id=frame.log_id,
                service=frame.service,
                method=frame.method,
                headers=list(frame.headers),
                payload=json.dumps({"code": 200}).encode("utf-8"),
            )
            try:
                await ws.send(ack.encode())
            except Exception:
                _log.exception("feishu ack failed instance=%s", self.instance_id)

    def _combine(self, frame: WsFrame) -> bytes | None:
        payload = frame.payload or b""
        try:
            total = int(frame.header(HEADER_SUM) or "1")
            seq = int(frame.header(HEADER_SEQ) or "0")
        except ValueError:
            return payload
        if total <= 1:
            return payload
        msg_id = frame.header(HEADER_MESSAGE_ID) or ""
        buf = self._fragments.get(msg_id)
        if buf is None or len(buf) != total:
            buf = [None] * total
            self._fragments[msg_id] = buf
        if 0 <= seq < total:
            buf[seq] = payload
        if any(part is None for part in buf):
            return None
        self._fragments.pop(msg_id, None)
        return b"".join(part or b"" for part in buf)


async def _default_connect(url: str):
    import inspect
    import websockets

    kwargs: dict = {}
    params = inspect.signature(websockets.connect).parameters
    if "proxy" in params:
        kwargs["proxy"] = None
    return await websockets.connect(url, **kwargs)
