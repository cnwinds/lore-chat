"""沙箱工具：run / stop / list / read / publish / stage / job_status（薄 adapter）。"""

from __future__ import annotations

from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.pending import PendingStore
from app.engine.sandbox.command_gate import SandboxCommandGate
from app.engine.sandbox.command_prep import prepare_streaming_command
from app.engine.sandbox.execution_engine import SandboxExecutionEngine
from app.engine.sandbox.kb_exchange import KbSandboxExchange
from app.engine.sandbox.protocol import SandboxRuntime


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
    ) -> None:
        self.runtime = runtime
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

    def _require(self) -> SandboxRuntime | dict:
        if self.runtime is None:
            return {
                "summary": "当前实例未启用沙箱执行能力（请用 docker-compose.sandbox.yml 启动）",
                "sources": [],
                "error": "sandbox disabled",
            }
        return self.runtime

    @staticmethod
    def _parse_run_args(args: dict) -> tuple[str | None, str, str | None, float, str]:
        cwd = (args.get("cwd") or "/workspace").strip() or "/workspace"
        command = (args.get("command") or "").strip() or None
        execution_id = (args.get("execution_id") or "").strip() or None
        wait = args.get("wait_sec")
        wait_sec = float(wait) if wait is not None else SandboxExecutionEngine.DEFAULT_WAIT_SEC
        if_exceeded = (args.get("if_exceeded") or "return").strip().lower()
        return command, cwd, execution_id, wait_sec, if_exceeded

    async def sandbox_run(self, args: dict) -> dict:
        rt = self._require()
        if isinstance(rt, dict):
            return rt
        command, cwd, execution_id, wait_sec, if_exceeded = self._parse_run_args(args)

        if not execution_id and not command:
            return {"summary": "缺少 command", "sources": [], "error": "missing command"}

        if not execution_id:
            gate = self.command_gate.maybe_confirm(args, command or "")
            if gate is not None:
                return gate
            command = prepare_streaming_command(command or "")

        await rt.ensure_ready()

        if execution_id:
            return await self.execution_engine.execute(
                rt,
                execution_id=execution_id,
                cwd=cwd,
                wait_sec=wait_sec,
                if_exceeded=if_exceeded,
            )
        return await self.execution_engine.execute(
            rt,
            command=command,
            cwd=cwd,
            wait_sec=wait_sec,
            if_exceeded=if_exceeded,
        )

    async def sandbox_stop(self, args: dict) -> dict:
        rt = self._require()
        if isinstance(rt, dict):
            return rt
        eid = (args.get("execution_id") or "").strip()
        if not eid:
            return {
                "summary": "缺少 execution_id",
                "sources": [],
                "error": "missing execution_id",
            }
        await rt.ensure_ready()
        return await self.execution_engine.stop(rt, eid)

    async def sandbox_job_status(self, args: dict) -> dict:
        rt = self._require()
        if isinstance(rt, dict):
            return rt
        eid = (args.get("execution_id") or "").strip()
        if not eid:
            return {
                "summary": "缺少 execution_id",
                "sources": [],
                "error": "missing execution_id",
            }
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

    async def sandbox_list_dir(self, args: dict) -> dict:
        rt = self._require()
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

    async def sandbox_read_file(self, args: dict) -> dict:
        rt = self._require()
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

    async def publish_from_sandbox(self, args: dict) -> dict:
        rt = self._require()
        if isinstance(rt, dict):
            return rt
        return await self.exchange.publish(rt, args, allow_binary=True)

    async def stage_to_sandbox(self, args: dict) -> dict:
        rt = self._require()
        if isinstance(rt, dict):
            return rt
        return await self.exchange.stage(rt, args)
