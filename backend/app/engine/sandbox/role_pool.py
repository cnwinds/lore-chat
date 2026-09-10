"""每角色固定绑定一个执行沙箱；控制面仍是单一 opensandbox-server。

P1：`sandbox_max_roles` 硬上限；空闲 TTL 只 destroy 容器、保留 PVC 与 slot。
永不借用其他角色的 sandbox。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path

from app.engine.roles import DEFAULT_ROLE_ID
from app.engine.sandbox import state as sandbox_state
from app.engine.sandbox.naming import DEFAULT_WORKSPACE_VOLUME
from app.engine.sandbox.protocol import SandboxRuntime

_log = logging.getLogger(__name__)

RuntimeFactory = Callable[[str, dict], SandboxRuntime]

POOL_FULL_ERROR = "sandbox_pool_full"


class SandboxPoolFullError(RuntimeError):
    """池已满且无法回收空闲 slot；工具应原样返回中文 summary。"""

    error = POOL_FULL_ERROR

    def __init__(self, max_roles: int) -> None:
        self.max_roles = max_roles
        super().__init__(
            f"沙箱池已满（最多同时 {max_roles} 个角色占用执行沙箱）。"
            "请等待其他角色空闲后再试，或在设置中提高「最大并行角色数」。"
            "不会借用其他角色的沙箱。"
        )


def runtime_has_active_executions(runtime: SandboxRuntime) -> bool:
    active = getattr(runtime, "_active_executions", None)
    if active:
        return True
    jobs = getattr(runtime, "_jobs", None)
    if isinstance(jobs, dict):
        return any(bool(getattr(job, "running", False)) for job in jobs.values())
    return False


class RoleSandboxPool:
    """角色沙箱池：get(role_id) 返回该角色专属 runtime，永不借用其他角色 slot。"""

    def __init__(
        self,
        *,
        kb_path: Path,
        runtime_factory: RuntimeFactory,
        default_volume: str = DEFAULT_WORKSPACE_VOLUME,
        mirror_region: str = "cn",
        max_roles: int | None = 4,
        idle_ttl_sec: float = 3600,
        destroy_volume_on_role_delete: bool = False,
    ) -> None:
        self.kb_path = Path(kb_path)
        self._factory = runtime_factory
        self.default_volume = default_volume
        self.mirror_region = mirror_region
        self.max_roles = max_roles
        self.idle_ttl_sec = idle_ttl_sec
        self.destroy_volume_on_role_delete = destroy_volume_on_role_delete
        self._runtimes: dict[str, SandboxRuntime] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_used: dict[str, float] = {}
        self._meta_lock = asyncio.Lock()
        self._reclaim_lock = asyncio.Lock()

    def _normalize_role_id(self, role_id: str | None) -> str:
        rid = (role_id or "").strip()
        return rid or DEFAULT_ROLE_ID

    def _effective_max(self) -> int | None:
        if self.max_roles is None:
            return None
        n = int(self.max_roles)
        return n if n > 0 else None

    def _touch(self, role_id: str, *, now: float | None = None) -> None:
        self._last_used[role_id] = time.monotonic() if now is None else now

    def _is_idle(self, role_id: str, runtime: SandboxRuntime, now: float) -> bool:
        if self.idle_ttl_sec is None or float(self.idle_ttl_sec) <= 0:
            return False
        if runtime_has_active_executions(runtime):
            return False
        last = self._last_used.get(role_id, now)
        return (now - last) >= float(self.idle_ttl_sec)

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
        destroy_volume_on_role_delete: bool | None = None,
        sandbox_env_update: dict[str, str] | None = None,
    ) -> None:
        """热更新镜像、池上限、空闲 TTL；已活 runtime 同步 mirror_env。"""
        from app.engine.sandbox.mirrors import mirror_env, normalize_mirror_region

        prefixes = ("PIP_", "UV_", "npm_", "LORECHAT_MIRROR")
        if mirror_region is not None:
            self.mirror_region = normalize_mirror_region(mirror_region)
        if max_roles is not None:
            self.max_roles = max_roles
        if idle_ttl_sec is not None:
            self.idle_ttl_sec = idle_ttl_sec
        if destroy_volume_on_role_delete is not None:
            self.destroy_volume_on_role_delete = bool(destroy_volume_on_role_delete)
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

    def pool_snapshot(self) -> dict:
        busy = [
            rid
            for rid, rt in self._runtimes.items()
            if runtime_has_active_executions(rt)
        ]
        cap = self._effective_max()
        return {
            "max": cap if cap is not None else 0,
            "active": len(self._runtimes),
            "busy_roles": sorted(busy),
        }

    async def _destroy_live(
        self,
        role_id: str,
        runtime: SandboxRuntime,
        *,
        keep_volume: bool,
    ) -> None:
        destroy = getattr(runtime, "destroy_container", None)
        if destroy is not None:
            await destroy(keep_volume=keep_volume)
        elif hasattr(runtime, "interrupt_all"):
            await runtime.interrupt_all()
        self._runtimes.pop(role_id, None)
        self._last_used.pop(role_id, None)
        if keep_volume:
            sandbox_state.mark_slot_reclaimable(
                self.kb_path,
                role_id,
                default_volume=self.default_volume,
            )
        else:
            sandbox_state.delete_slot(
                self.kb_path,
                role_id,
                default_volume=self.default_volume,
            )
        _log.info(
            "sandbox pool reclaimed role=%s keep_volume=%s",
            role_id,
            keep_volume,
        )

    async def _reclaim_idle_unlocked(self, *, exclude: str, now: float) -> list[str]:
        """回收超时空闲容器；调用方须持有 `_reclaim_lock`。"""
        reclaimed: list[str] = []
        candidates = [
            rid
            for rid, rt in list(self._runtimes.items())
            if rid != exclude and self._is_idle(rid, rt, now)
        ]
        for rid in candidates:
            lock = await self._lock_for(rid)
            async with lock:
                rt = self._runtimes.get(rid)
                if rt is None or not self._is_idle(rid, rt, time.monotonic()):
                    continue
                await self._destroy_live(rid, rt, keep_volume=True)
                reclaimed.append(rid)
        return reclaimed

    async def reclaim_idle(self) -> list[str]:
        """销毁超时且无活跃执行的容器，保留 PVC 与 slot。"""
        async with self._reclaim_lock:
            return await self._reclaim_idle_unlocked(
                exclude="", now=time.monotonic()
            )

    async def get(self, role_id: str) -> SandboxRuntime:
        """返回该角色固定 runtime；满员且无法回收空闲时抛 SandboxPoolFullError。"""
        rid = self._normalize_role_id(role_id)
        lock = await self._lock_for(rid)
        async with lock:
            existing = self._runtimes.get(rid)
            if existing is not None:
                self._touch(rid)
                await existing.ensure_ready()
                return existing

        async with self._reclaim_lock:
            async with lock:
                existing = self._runtimes.get(rid)
                if existing is not None:
                    self._touch(rid)
                    await existing.ensure_ready()
                    return existing
                await self._reclaim_idle_unlocked(exclude=rid, now=time.monotonic())
                cap = self._effective_max()
                if cap is not None and rid not in self._runtimes and len(self._runtimes) >= cap:
                    raise SandboxPoolFullError(cap)
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
                sandbox_state.upsert_slot(
                    self.kb_path,
                    rid,
                    sandbox_id=str(sid) if sid else None,
                    volume_name=slot.get("volume_name"),
                    mirror_region=self.mirror_region,
                    default_volume=self.default_volume,
                    reclaimable=False,
                )
                self._runtimes[rid] = rt
                self._touch(rid)
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

    async def release_role(self, role_id: str, *, destroy_volume: bool | None = None) -> None:
        """删除角色：中断执行，销毁容器；默认保留 PVC，按开关决定是否忘记 slot。"""
        rid = self._normalize_role_id(role_id)
        drop_volume = (
            self.destroy_volume_on_role_delete
            if destroy_volume is None
            else bool(destroy_volume)
        )
        lock = await self._lock_for(rid)
        async with lock:
            rt = self._runtimes.get(rid)
            if rt is not None:
                await self._destroy_live(rid, rt, keep_volume=not drop_volume)
                return
            if drop_volume:
                sandbox_state.delete_slot(
                    self.kb_path, rid, default_volume=self.default_volume
                )
            else:
                sandbox_state.mark_slot_reclaimable(
                    self.kb_path, rid, default_volume=self.default_volume
                )
            self._last_used.pop(rid, None)

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


__all__ = [
    "POOL_FULL_ERROR",
    "RoleSandboxPool",
    "RuntimeFactory",
    "SandboxPoolFullError",
    "parse_role_schedule_id",
    "runtime_has_active_executions",
]
