"""每角色固定绑定一个执行沙箱；控制面仍是单一 opensandbox-server。

P0：持久化 role→sandbox_id+volume，并行角色互不抢 /workspace、互不 interrupt。
P1：sandbox_max_roles / 空闲 TTL 销毁容器、保留 PVC（本模块只留挂钩，不回收）。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from app.engine.roles import DEFAULT_ROLE_ID
from app.engine.sandbox import state as sandbox_state
from app.engine.sandbox.naming import DEFAULT_WORKSPACE_VOLUME
from app.engine.sandbox.protocol import SandboxRuntime

_log = logging.getLogger(__name__)

RuntimeFactory = Callable[[str, dict], SandboxRuntime]


class RoleSandboxPool:
    """角色沙箱池：get(role_id) 返回该角色专属 runtime，永不借用其他角色 slot。"""

    def __init__(
        self,
        *,
        kb_path: Path,
        runtime_factory: RuntimeFactory,
        default_volume: str = DEFAULT_WORKSPACE_VOLUME,
        mirror_region: str = "cn",
        max_roles: int | None = None,
        idle_ttl_sec: float = 0,
    ) -> None:
        self.kb_path = Path(kb_path)
        self._factory = runtime_factory
        self.default_volume = default_volume
        self.mirror_region = mirror_region
        # P1：池上限 / 空闲回收。P0 只记录，不拒绝绑定、不 destroy 容器。
        self.max_roles = max_roles
        self.idle_ttl_sec = idle_ttl_sec
        self._runtimes: dict[str, SandboxRuntime] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._meta_lock = asyncio.Lock()

    def _normalize_role_id(self, role_id: str | None) -> str:
        rid = (role_id or "").strip()
        return rid or DEFAULT_ROLE_ID

    async def _lock_for(self, role_id: str) -> asyncio.Lock:
        async with self._meta_lock:
            lock = self._locks.get(role_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[role_id] = lock
            return lock

    def apply_settings(
        self,
        *,
        mirror_region: str | None = None,
        max_roles: int | None = None,
        idle_ttl_sec: float | None = None,
        sandbox_env_update: dict[str, str] | None = None,
    ) -> None:
        """热更新镜像与 P1 挂钩；已活 runtime 同步 mirror_env。"""
        from app.engine.sandbox.mirrors import mirror_env, normalize_mirror_region

        prefixes = ("PIP_", "UV_", "npm_", "LORECHAT_MIRROR")
        if mirror_region is not None:
            self.mirror_region = normalize_mirror_region(mirror_region)
        if max_roles is not None:
            self.max_roles = max_roles
        if idle_ttl_sec is not None:
            self.idle_ttl_sec = idle_ttl_sec
        region = self.mirror_region
        extra = dict(sandbox_env_update or {})
        for rt in self._runtimes.values():
            if hasattr(rt, "mirror_region"):
                rt.mirror_region = region
            if extra or hasattr(rt, "sandbox_env"):
                base = {
                    k: v
                    for k, v in (getattr(rt, "sandbox_env", None) or {}).items()
                    if not k.startswith(prefixes)
                }
                rt.sandbox_env = {**base, **mirror_env(region), **extra}

    def peek(self, role_id: str) -> SandboxRuntime | None:
        """已构造的进程内 runtime；不创建、不 ensure。"""
        return self._runtimes.get(self._normalize_role_id(role_id))

    def binding(self, role_id: str) -> dict | None:
        return sandbox_state.get_slot(
            self.kb_path,
            self._normalize_role_id(role_id),
            default_volume=self.default_volume,
        )

    async def get(self, role_id: str) -> SandboxRuntime:
        """返回该角色固定 runtime；ensure_ready 带 per-role lock。"""
        rid = self._normalize_role_id(role_id)
        lock = await self._lock_for(rid)
        async with lock:
            existing = self._runtimes.get(rid)
            if existing is not None:
                await existing.ensure_ready()
                return existing
            # P1 将在此按 max_roles 拒绝或驱逐空闲 slot；P0 仍创建绑定。
            if (
                self.max_roles
                and rid not in self._runtimes
                and len(self._runtimes) >= int(self.max_roles)
            ):
                _log.warning(
                    "sandbox_max_roles=%s reached (P1 will reject/evict); "
                    "P0 still binds role=%s",
                    self.max_roles,
                    rid,
                )
            slot = sandbox_state.ensure_slot(
                self.kb_path,
                rid,
                default_volume=self.default_volume,
                mirror_region=self.mirror_region,
            )
            rt = self._factory(rid, slot)
            if hasattr(rt, "workspace_volume") and slot.get("volume_name"):
                rt.workspace_volume = slot["volume_name"]
            if hasattr(rt, "role_id"):
                rt.role_id = rid
            if hasattr(rt, "mirror_region"):
                rt.mirror_region = self.mirror_region
            await rt.ensure_ready()
            sid = getattr(rt, "_sandbox_id", None) or getattr(rt, "sandbox_id", None)
            if sid:
                sandbox_state.upsert_slot(
                    self.kb_path,
                    rid,
                    sandbox_id=str(sid),
                    volume_name=slot.get("volume_name"),
                    mirror_region=self.mirror_region,
                    default_volume=self.default_volume,
                )
            self._runtimes[rid] = rt
            _log.info(
                "sandbox pool bound role=%s volume=%s sandbox_id=%s",
                rid,
                slot.get("volume_name"),
                sid,
            )
            return rt

    async def interrupt_role(self, role_id: str) -> None:
        """只中断该角色 runtime 上的执行，不碰其他角色。"""
        rid = self._normalize_role_id(role_id)
        rt = self._runtimes.get(rid)
        if rt is None:
            return
        if hasattr(rt, "interrupt_all"):
            await rt.interrupt_all()

    async def interrupt_execution(
        self,
        execution_id: str,
        *,
        role_id: str | None = None,
    ) -> None:
        """中断指定 execution；有 role_id 时绝不落到其他角色的 runtime。"""
        eid = (execution_id or "").strip()
        if not eid:
            return
        if role_id:
            rid = self._normalize_role_id(role_id)
            rt = self._runtimes.get(rid)
            if rt is not None:
                await rt.interrupt(eid)
            return
        for rid, rt in self._runtimes.items():
            active = getattr(rt, "_active_executions", None)
            jobs = getattr(rt, "_jobs", None)
            if active is not None and eid in active:
                await rt.interrupt(eid)
                return
            if isinstance(jobs, dict) and eid in jobs:
                await rt.interrupt(eid)
                return

    def live_role_ids(self) -> list[str]:
        return sorted(self._runtimes)


def parse_role_schedule_id(client_message_id: str | None) -> str | None:
    """role-schedule:{schedule_id}:{nonce} → schedule_id。"""
    cmid = str(client_message_id or "")
    prefix = "role-schedule:"
    if not cmid.startswith(prefix):
        return None
    rest = cmid[len(prefix) :]
    sid = rest.split(":", 1)[0].strip()
    return sid or None


__all__ = ["RoleSandboxPool", "RuntimeFactory", "parse_role_schedule_id"]
