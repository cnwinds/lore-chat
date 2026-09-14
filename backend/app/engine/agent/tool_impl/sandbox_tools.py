"""沙箱工具：run / stop / list / read / publish / stage / job_status（薄 adapter）。"""

from __future__ import annotations

import shlex

from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.pending import PendingStore
from app.engine.roles import DEFAULT_ROLE_ID, DEFAULT_ROLE_NAME
from app.engine.sandbox.command_gate import SandboxCommandGate
from app.engine.sandbox.command_prep import prepare_streaming_command
from app.engine.sandbox.execution_engine import SandboxExecutionEngine
from app.engine.sandbox.kb_exchange import KbSandboxExchange
from app.engine.sandbox.protocol import SandboxRuntime
from app.engine.sandbox.role_pool import (
    RoleSandboxPool,
    SandboxPoolFullError,
    parse_role_schedule_id,
)
from app.engine.sandbox.workspace_cwd import resolve_sandbox_cwd


class SandboxTools:
    def __init__(
        self,
        runtime: SandboxRuntime | None,
        knowledge_writer: KnowledgeWriter,
        pending: PendingStore | None = None,
        *,
        trust_mode: bool = True,
        default_wait_sec: float = SandboxExecutionEngine.DEFAULT_WAIT_SEC,
        poll_interval_sec: float = SandboxExecutionEngine.DEFAULT_POLL_INTERVAL,
        read_max_chars: int = 50_000,
        pool: RoleSandboxPool | None = None,
        conversations=None,
        roles=None,
    ) -> None:
        self.runtime = runtime
        self.pool = pool
        self.conversations = conversations
        self.roles = roles
        self.knowledge_writer = knowledge_writer
        self.pending = pending
        self.command_gate = SandboxCommandGate(pending, trust_mode=trust_mode)
        self.exchange = KbSandboxExchange(knowledge_writer)
        self.execution_engine = SandboxExecutionEngine(
            poll_interval_sec=poll_interval_sec,
        )
        self.default_wait_sec = default_wait_sec
        self.read_max_chars = read_max_chars

    @property
    def trust_mode(self) -> bool:
        return self.command_gate.trust_mode

    @trust_mode.setter
    def trust_mode(self, value: bool) -> None:
        self.command_gate.trust_mode = value

    @property
    def available(self) -> bool:
        return self.pool is not None or self.runtime is not None

    def _disabled(self) -> dict:
        return {
            "summary": "当前实例未启用沙箱执行能力（请用 docker-compose.sandbox.yml 启动）",
            "sources": [],
            "error": "sandbox disabled",
        }

    def _resolve_role_id(
        self,
        args: dict,
        conversation_id: str | None = None,
    ) -> str:
        """会话角色优先，避免模型传 role_id 借用其他角色 slot。"""
        if conversation_id and self.conversations is not None:
            try:
                return self.conversations.get_role_id(conversation_id)
            except KeyError:
                pass
        rid = (args.get("role_id") or "").strip()
        if rid:
            return rid
        return DEFAULT_ROLE_ID

    def _role_name(self, role_id: str) -> str | None:
        if self.roles is not None:
            try:
                name = str(self.roles.get(role_id).get("name") or "").strip()
                if name:
                    return name
            except KeyError:
                pass
        if role_id == DEFAULT_ROLE_ID:
            return DEFAULT_ROLE_NAME
        return None

    def _resolve_schedule_id(
        self,
        args: dict,
        conversation_id: str | None = None,
    ) -> str | None:
        sid = (args.get("schedule_id") or "").strip()
        if sid:
            return sid
        if not conversation_id or self.conversations is None:
            return None
        try:
            for turn in self.conversations.list_running_turns():
                if turn.get("conversation_id") != conversation_id:
                    continue
                parsed = parse_role_schedule_id(turn.get("client_message_id"))
                if parsed:
                    return parsed
        except Exception:
            return None
        return None

    async def _runtime_for(
        self,
        args: dict,
        *,
        conversation_id: str | None = None,
        role_id: str | None = None,
    ) -> SandboxRuntime | dict:
        if self.pool is None and self.runtime is None:
            return self._disabled()
        if self.pool is None:
            return self.runtime  # 单测单 runtime：不发明其他角色 slot
        rid = role_id or self._resolve_role_id(args, conversation_id)
        try:
            return await self.pool.get(rid)
        except SandboxPoolFullError as e:
            return {
                "summary": str(e),
                "sources": [],
                "error": e.error,
            }

    async def _runtime_for_execution(
        self,
        execution_id: str,
        args: dict,
        *,
        conversation_id: str | None = None,
    ) -> SandboxRuntime | dict:
        rec = self.execution_engine.registry.get(execution_id)
        if rec and rec.role_id and self.pool is not None:
            try:
                return await self.pool.get(rec.role_id)
            except SandboxPoolFullError as e:
                return {
                    "summary": str(e),
                    "sources": [],
                    "error": e.error,
                }
        return await self._runtime_for(args, conversation_id=conversation_id)

    async def _ensure_cwd(self, runtime: SandboxRuntime, cwd: str) -> None:
        if cwd in ("", "/", "/workspace"):
            return
        quoted = shlex.quote(cwd)
        run = getattr(runtime, "run", None)
        if run is None:
            return
        try:
            await run(f"mkdir -p -- {quoted}", cwd="/", timeout_sec=30)
        except TypeError:
            await run(f"mkdir -p -- {quoted}", cwd="/")

    @staticmethod
    def _parse_run_flags(args: dict) -> tuple[str | None, str | None, float, str]:
        command = (args.get("command") or "").strip() or None
        execution_id = (args.get("execution_id") or "").strip() or None
        wait = args.get("wait_sec")
        wait_sec = (
            float(wait) if wait is not None else SandboxExecutionEngine.DEFAULT_WAIT_SEC
        )
        if_exceeded = (args.get("if_exceeded") or "return").strip().lower()
        return command, execution_id, wait_sec, if_exceeded

    async def sandbox_run(
        self,
        args: dict,
        *,
        conversation_id: str | None = None,
        schedule_id: str | None = None,
    ) -> dict:
        cid = conversation_id or (args.get("conversation_id") or "").strip() or None
        sid = schedule_id or self._resolve_schedule_id(args, cid)
        role_id = self._resolve_role_id(args, cid)
        cwd_or_err = resolve_sandbox_cwd(args, conversation_id=cid, schedule_id=sid)
        if isinstance(cwd_or_err, dict):
            return cwd_or_err
        cwd = cwd_or_err

        command, execution_id, wait_sec, if_exceeded = self._parse_run_flags(args)
        if not execution_id and not command:
            return {"summary": "缺少 command", "sources": [], "error": "missing command"}

        if not execution_id:
            skip_gate = False
            if cid and self.conversations is not None:
                try:
                    from app.engine.channel_plugins.types import is_channel_origin

                    skip_gate = is_channel_origin(self.conversations.get_origin(cid))
                except KeyError:
                    skip_gate = False
            if not skip_gate:
                gate = self.command_gate.maybe_confirm(
                    args,
                    command or "",
                    role_id=role_id,
                    role_name=self._role_name(role_id),
                    conversation_id=cid,
                    schedule_id=sid,
                    cwd=cwd,
                )
                if gate is not None:
                    return gate
            command = prepare_streaming_command(command or "")

        rt = await self._runtime_for(args, conversation_id=cid, role_id=role_id)
        if isinstance(rt, dict):
            return rt
        await rt.ensure_ready()
        if not execution_id:
            await self._ensure_cwd(rt, cwd)

        kwargs = dict(
            cwd=cwd,
            wait_sec=wait_sec,
            if_exceeded=if_exceeded,
            role_id=role_id,
            conversation_id=cid,
            schedule_id=sid,
        )
        if execution_id:
            return await self.execution_engine.execute(
                rt, execution_id=execution_id, **kwargs
            )
        return await self.execution_engine.execute(rt, command=command, **kwargs)

    async def sandbox_stop(
        self,
        args: dict,
        *,
        conversation_id: str | None = None,
    ) -> dict:
        eid = (args.get("execution_id") or "").strip()
        if not eid:
            return {
                "summary": "缺少 execution_id",
                "sources": [],
                "error": "missing execution_id",
            }
        cid = conversation_id or (args.get("conversation_id") or "").strip() or None
        rec = self.execution_engine.registry.get(eid)
        if rec and cid and rec.conversation_id and rec.conversation_id != cid:
            return {
                "summary": "execution_id 不属于当前会话，已拒绝跨会话停止",
                "sources": [],
                "error": "execution not in conversation",
            }
        rt = await self._runtime_for_execution(eid, args, conversation_id=cid)
        if isinstance(rt, dict):
            return rt
        await rt.ensure_ready()
        return await self.execution_engine.stop(rt, eid)

    async def sandbox_job_status(
        self,
        args: dict,
        *,
        conversation_id: str | None = None,
    ) -> dict:
        eid = (args.get("execution_id") or "").strip()
        if not eid:
            return {
                "summary": "缺少 execution_id",
                "sources": [],
                "error": "missing execution_id",
            }
        cid = conversation_id or (args.get("conversation_id") or "").strip() or None
        rt = await self._runtime_for_execution(eid, args, conversation_id=cid)
        if isinstance(rt, dict):
            return rt
        await rt.ensure_ready()
        status = await rt.poll_job(eid, log_cursor=None)
        state = "running" if status.running else f"exit={status.exit_code}"
        logs = (status.logs or "").strip()
        summary = f"job {eid}: {state}"
        if logs:
            summary += f"\n{logs[:3500]}"
        return {
            "summary": summary,
            "sources": [],
            "execution_id": eid,
            "running": status.running,
            "exit_code": status.exit_code,
            "stdout": status.logs,
        }

    async def sandbox_list_dir(
        self,
        args: dict,
        *,
        conversation_id: str | None = None,
    ) -> dict:
        rt = await self._runtime_for(args, conversation_id=conversation_id)
        if isinstance(rt, dict):
            return rt
        path = (args.get("path") or "/workspace").strip() or "/workspace"
        await rt.ensure_ready()
        entries = await rt.list_dir(path)
        # 路径权威在 entries[]；summary 仅单行计数，避免 JSON 转义换行导致模型粘连文件名
        if entries:
            summary = f"{path} 共 {len(entries)} 项；路径见 entries"
        else:
            summary = f"{path} 为空"
        return {
            "summary": summary,
            "sources": [],
            "path": path,
            "count": len(entries),
            "entries": [
                {
                    "name": e.name,
                    "path": e.path,
                    "is_dir": e.is_dir,
                    "kind": "dir" if e.is_dir else "file",
                }
                for e in entries
            ],
        }

    async def sandbox_read_file(
        self,
        args: dict,
        *,
        conversation_id: str | None = None,
    ) -> dict:
        rt = await self._runtime_for(args, conversation_id=conversation_id)
        if isinstance(rt, dict):
            return rt
        path = (args.get("path") or "").strip()
        if not path:
            return {"summary": "缺少 path", "sources": [], "error": "missing path"}
        max_chars = int(args.get("max_chars") or self.read_max_chars)
        await rt.ensure_ready()
        try:
            data = await rt.read_file(path, max_bytes=max_chars * 4)
        except FileNotFoundError:
            return {
                "summary": f"文件不存在：{path}",
                "sources": [],
                "error": "not found",
            }
        text = data.decode("utf-8", errors="replace")
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]
        return {
            "summary": f"已读 {path}" + ("（已截断）" if truncated else ""),
            "sources": [],
            "content": text,
            "truncated": truncated,
            "path": path,
        }

    async def publish_from_sandbox(
        self,
        args: dict,
        *,
        conversation_id: str | None = None,
    ) -> dict:
        rt = await self._runtime_for(args, conversation_id=conversation_id)
        if isinstance(rt, dict):
            return rt
        return await self.exchange.publish(rt, args, allow_binary=True)

    async def stage_to_sandbox(
        self,
        args: dict,
        *,
        conversation_id: str | None = None,
    ) -> dict:
        rt = await self._runtime_for(args, conversation_id=conversation_id)
        if isinstance(rt, dict):
            return rt
        return await self.exchange.stage(rt, args)
