"""沙箱工具：run / list / read / publish / stage / job_status（薄 adapter）。"""

from __future__ import annotations

import asyncio

from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.pending import PendingStore
from app.engine.sandbox.command_gate import SandboxCommandGate
from app.engine.sandbox.job_runner import SandboxJobRunner
from app.engine.sandbox.kb_exchange import KbSandboxExchange
from app.engine.sandbox.progress import emit_progress
from app.engine.sandbox.protocol import SandboxRuntime


class SandboxTools:
    def __init__(
        self,
        runtime: SandboxRuntime | None,
        knowledge_writer: KnowledgeWriter,
        pending: PendingStore | None = None,
        *,
        trust_mode: bool = True,
        short_timeout_sec: float = 120,
        job_poll_interval_sec: float = 0.5,
        job_max_wait_sec: float = 600,
        read_max_chars: int = 50_000,
    ) -> None:
        self.runtime = runtime
        self.knowledge_writer = knowledge_writer
        self.pending = pending
        self.command_gate = SandboxCommandGate(pending, trust_mode=trust_mode)
        self.exchange = KbSandboxExchange(knowledge_writer)
        self.job_runner = SandboxJobRunner(
            poll_interval_sec=job_poll_interval_sec,
            max_wait_sec=job_max_wait_sec,
        )
        self.short_timeout_sec = short_timeout_sec
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
    def _parse_run_args(args: dict) -> tuple[str, str, bool, float | None]:
        cwd = (args.get("cwd") or "/workspace").strip() or "/workspace"
        background = bool(args.get("background", False))
        timeout = args.get("timeout_sec")
        timeout_sec = float(timeout) if timeout is not None else None
        command = (args.get("command") or "").strip()
        return command, cwd, background, timeout_sec

    async def sandbox_run(self, args: dict) -> dict:
        rt = self._require()
        if isinstance(rt, dict):
            return rt
        command, cwd, background, timeout = self._parse_run_args(args)
        if not command:
            return {"summary": "缺少 command", "sources": [], "error": "missing command"}

        gate = self.command_gate.maybe_confirm(args, command)
        if gate is not None:
            return gate

        timeout_sec = (
            float(timeout) if timeout is not None else self.short_timeout_sec
        )

        await rt.ensure_ready()

        if background or timeout_sec > self.short_timeout_sec:
            return await self.job_runner.wait(rt, command, cwd=cwd)

        try:
            result = await rt.run(command, cwd=cwd, timeout_sec=timeout_sec)
        except asyncio.CancelledError:
            raise
        body = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        emit_progress(f"\n[exit {result.exit_code}]", phase="end")
        summary_parts = [f"exit={result.exit_code}"]
        if body:
            summary_parts.append(body[:3500])
        if err:
            summary_parts.append(f"stderr:\n{err[:1000]}")
        out = {
            "summary": "\n".join(summary_parts),
            "sources": [],
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        if result.exit_code != 0:
            out["error"] = f"exit_code={result.exit_code}"
        return out

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
        lines = [f"{'d' if e.is_dir else 'f'} {e.path}" for e in entries]
        preview = "\n".join(lines[:200])
        return {
            "summary": f"{path} 共 {len(entries)} 项\n{preview}" if entries else f"{path} 为空",
            "sources": [],
            "entries": [
                {"name": e.name, "path": e.path, "is_dir": e.is_dir} for e in entries
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
