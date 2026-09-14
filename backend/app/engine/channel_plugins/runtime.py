"""长连接运行时：按启用实例启停飞书 WS，入站投递给 ChannelTurnService。"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from app.engine.channel_plugins.feishu import FEISHU_TYPE_ID, INGRESS_WEBSOCKET, FeishuAdapter
from app.engine.channel_plugins.feishu_ws import FeishuWsSession
from app.engine.channel_plugins.types import STATUS_ENABLED, STATUS_ERROR

_log = logging.getLogger(__name__)


class ChannelRuntime:
    def __init__(
        self,
        *,
        registry,
        instances,
        turn_service,
        runtime_store,
        settings=None,
        start_connections: bool | None = None,
    ):
        self.registry = registry
        self.instances = instances
        self.turn_service = turn_service
        self.runtime_store = runtime_store
        self.settings = settings
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sessions: dict[str, FeishuWsSession] = {}
        if start_connections is None:
            start_connections = "pytest" not in sys.modules
        self.start_connections = start_connections
        self._session_factory = FeishuWsSession

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self.turn_service.attach_loop(loop)

    def public_base_url(self) -> str | None:
        settings = self.settings
        if settings is None:
            return None
        return (getattr(settings, "public_base_url", None) or "").strip() or None

    def start_enabled(self) -> None:
        if not self.start_connections:
            return
        for inst in self.instances.list_all():
            if inst.get("enabled") and inst.get("status") == STATUS_ENABLED:
                try:
                    self.start_instance(inst["id"])
                except Exception:
                    _log.exception("channel start failed id=%s", inst.get("id"))

    def start_instance(self, instance_id: str) -> None:
        if not self.start_connections:
            return
        inst = self.instances.get_internal(instance_id)
        if inst.get("type_id") != FEISHU_TYPE_ID:
            adapter = self.registry.get(inst["type_id"])
            adapter.start(inst)
            return
        if (inst.get("config") or {}).get("ingress", INGRESS_WEBSOCKET) != INGRESS_WEBSOCKET:
            return
        if not inst.get("enabled") or inst.get("status") != STATUS_ENABLED:
            return
        loop = self._loop
        if loop is None:
            return
        existing = self._sessions.get(instance_id)
        if existing is not None:
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                loop.create_task(self._restart(instance_id))
                return
            self.stop_instance(instance_id)
        secrets = inst.get("secrets") or {}
        config = inst.get("config") or {}
        app_id = str(config.get("app_id") or "").strip()
        app_secret = str(secrets.get("app_secret") or "").strip()
        if not app_id or not app_secret:
            self.instances.update(
                instance_id,
                status=STATUS_ERROR,
                status_detail="缺少 App ID / App Secret",
            )
            return

        def on_payload(body: dict[str, Any]) -> None:
            adapter = self.registry.get(FEISHU_TYPE_ID)
            event = adapter.parse_inbound({"instance_id": instance_id, "body": body})
            self.turn_service.enqueue_now(event)

        def on_status(status: str, detail: str | None) -> None:
            try:
                current = self.instances.get(instance_id)
            except KeyError:
                return
            if not current.get("enabled"):
                return
            self.instances.update(instance_id, status=status, status_detail=detail)
            if status == STATUS_ERROR:
                self.runtime_store.add_log(
                    instance_id,
                    kind="connection",
                    level="error",
                    message=detail or "长连接异常",
                )
            elif status == STATUS_ENABLED:
                self.runtime_store.add_log(
                    instance_id,
                    kind="connection",
                    message="长连接已建立",
                )

        session = self._session_factory(
            instance_id=instance_id,
            app_id=app_id,
            app_secret=app_secret,
            on_payload=on_payload,
            on_status=on_status,
        )
        self._sessions[instance_id] = session
        session.start(loop)
        adapter = self.registry.get(FEISHU_TYPE_ID)
        if isinstance(adapter, FeishuAdapter):
            adapter.start(inst)

    async def _restart(self, instance_id: str) -> None:
        session = self._sessions.pop(instance_id, None)
        if session is not None:
            await session.astop()
        if instance_id not in self._sessions:
            self.start_instance(instance_id)

    def stop_instance(self, instance_id: str) -> None:
        session = self._sessions.pop(instance_id, None)
        loop = self._loop
        if session is not None and loop is not None:
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                loop.create_task(session.astop())
            else:
                fut = asyncio.run_coroutine_threadsafe(session.astop(), loop)
                try:
                    fut.result(timeout=3)
                except Exception:
                    _log.warning("feishu ws stop timeout id=%s", instance_id)
        try:
            inst = self.instances.get_internal(instance_id)
            self.registry.get(inst["type_id"]).stop(inst)
        except (KeyError, Exception):
            pass

    def sync_instance(self, instance_id: str) -> None:
        try:
            inst = self.instances.get(instance_id)
        except KeyError:
            self.stop_instance(instance_id)
            return
        if (
            inst.get("enabled")
            and inst.get("status") == STATUS_ENABLED
            and inst.get("type_id") == FEISHU_TYPE_ID
        ):
            self.start_instance(instance_id)
        else:
            self.stop_instance(instance_id)

    async def ashutdown(self) -> None:
        sessions = list(self._sessions.values())
        self._sessions.clear()
        if sessions:
            await asyncio.gather(*(item.astop() for item in sessions), return_exceptions=True)
        try:
            adapter = self.registry.get(FEISHU_TYPE_ID)
        except Exception:
            return
        close = getattr(adapter, "close", None)
        if callable(close):
            close()

    def shutdown(self) -> None:
        loop = self._loop
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop and loop is not None:
            loop.create_task(self.ashutdown())
            return
        ids = list(self._sessions)
        for instance_id in ids:
            self.stop_instance(instance_id)
        try:
            adapter = self.registry.get(FEISHU_TYPE_ID)
        except Exception:
            return
        close = getattr(adapter, "close", None)
        if callable(close):
            close()
