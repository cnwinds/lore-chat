"""长连接运行时：按启用实例启停 websocket，入站投递给 ChannelTurnService。"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

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
        self._sessions: dict[str, Any] = {}
        if start_connections is None:
            start_connections = "pytest" not in sys.modules
        self.start_connections = start_connections

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
        if not inst.get("enabled") or inst.get("status") != STATUS_ENABLED:
            return
        loop = self._loop
        adapter = self.registry.get(inst["type_id"])
        existing = self._sessions.get(instance_id)
        if existing is not None:
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop and loop is not None:
                loop.create_task(self._restart(instance_id))
                return
            self.stop_instance(instance_id)

        def on_payload(body: dict[str, Any]) -> None:
            raw = body
            if isinstance(body, dict) and "instance_id" not in body:
                raw = {"instance_id": instance_id, "body": body}
            event = adapter.parse_inbound(raw)
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

        factory = getattr(adapter, "create_session", None)
        session = None
        if callable(factory):
            session = factory(inst, on_payload=on_payload, on_status=on_status)
        if session is not None:
            if loop is None:
                return
            self._sessions[instance_id] = session
            session.start(loop)
        start = getattr(adapter, "start", None)
        if callable(start):
            start(inst)

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
                    _log.warning("channel ws stop timeout id=%s", instance_id)
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
        if inst.get("enabled") and inst.get("status") == STATUS_ENABLED:
            self.start_instance(instance_id)
        else:
            self.stop_instance(instance_id)

    async def ashutdown(self) -> None:
        sessions = list(self._sessions.values())
        self._sessions.clear()
        if sessions:
            await asyncio.gather(*(item.astop() for item in sessions), return_exceptions=True)
        self._close_adapters()

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
        self._close_adapters()

    def _close_adapters(self) -> None:
        for type_id in ("feishu", "slack", "wecom", "dingtalk"):
            try:
                adapter = self.registry.get(type_id)
            except Exception:
                continue
            close = getattr(adapter, "close", None)
            if callable(close):
                close()
