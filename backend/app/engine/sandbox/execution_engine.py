"""沙箱命令统一执行：后台 job + poll 流式 + wait 预算检查点。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from app.engine.chat.progress_log import ensure_line_chunk
from app.engine.sandbox.execution_registry import ExecutionRegistry
from app.engine.sandbox.progress import emit_progress
from app.engine.sandbox.protocol import SandboxRuntime

ProgressEmit = Callable[..., None]

VALID_IF_EXCEEDED = frozenset({"return", "wait_until_done", "stop"})


class SandboxExecutionEngine:
    DEFAULT_WAIT_SEC = 60.0
    DEFAULT_POLL_INTERVAL = 0.2

    def __init__(
        self,
        registry: ExecutionRegistry | None = None,
        *,
        poll_interval_sec: float = DEFAULT_POLL_INTERVAL,
        emit: ProgressEmit | None = None,
    ) -> None:
        self.registry = registry or ExecutionRegistry()
        self.poll_interval_sec = poll_interval_sec
        self._emit = emit or emit_progress

    async def execute(
        self,
        runtime: SandboxRuntime,
        *,
        command: str | None = None,
        execution_id: str | None = None,
        cwd: str = "/workspace",
        wait_sec: float = DEFAULT_WAIT_SEC,
        if_exceeded: str = "return",
    ) -> dict:
        mode = (if_exceeded or "return").strip().lower()
        if mode not in VALID_IF_EXCEEDED:
            return {
                "summary": f"无效的 if_exceeded={if_exceeded!r}，"
                f"可选：{', '.join(sorted(VALID_IF_EXCEEDED))}",
                "sources": [],
                "error": "invalid if_exceeded",
            }

        wait_sec = max(0.1, float(wait_sec))
        unlimited = mode == "wait_until_done"

        if execution_id:
            rec = self.registry.get(execution_id)
            if rec is None:
                return {
                    "summary": f"未知 execution_id={execution_id}",
                    "sources": [],
                    "error": "unknown execution_id",
                }
            eid = execution_id
            cursor = rec.log_cursor
            cwd = rec.cwd
            full_logs = rec.accumulated_logs
        else:
            if not (command or "").strip():
                return {
                    "summary": "缺少 command（新任务）或 execution_id（续接）",
                    "sources": [],
                    "error": "missing command",
                }
            eid = await runtime.start_job(command.strip(), cwd=cwd)
            self._emit(f"job started id={eid}\n", phase="job", execution_id=eid)
            self.registry.register(eid, command.strip(), cwd=cwd)
            cursor = None
            full_logs = ""

        wait_start = time.monotonic()
        try:
            while True:
                status = await runtime.poll_job(eid, log_cursor=cursor)
                chunk = status.logs or ""
                if chunk:
                    full_logs += chunk
                    self._emit(
                        ensure_line_chunk(chunk),
                        phase="log",
                        execution_id=eid,
                    )
                if status.next_cursor is not None:
                    cursor = status.next_cursor
                self.registry.update_cursor(eid, cursor, full_logs)

                if not status.running:
                    code = status.exit_code if status.exit_code is not None else 0
                    self._emit(f"\n[exit {code}]", phase="end", execution_id=eid)
                    self.registry.remove(eid)
                    summary = (
                        f"命令完成 exit={code}"
                        + (f"\n{full_logs.strip()}" if full_logs.strip() else "")
                    )
                    out = {
                        "summary": summary[:4000],
                        "sources": [],
                        "exit_code": code,
                        "execution_id": eid,
                        "stdout": full_logs,
                        "running": False,
                        "checkpoint": False,
                    }
                    if code != 0:
                        out["error"] = f"exit_code={code}"
                    return out

                if not unlimited and (time.monotonic() - wait_start) >= wait_sec:
                    elapsed = self.registry.elapsed_sec(eid)
                    if mode == "stop":
                        await runtime.interrupt(eid)
                        final = await runtime.poll_job(eid, log_cursor=cursor)
                        tail = final.logs or ""
                        if tail:
                            full_logs += tail
                            self._emit(
                                ensure_line_chunk(tail),
                                phase="log",
                                execution_id=eid,
                            )
                        code = final.exit_code if final.exit_code is not None else -1
                        self._emit(f"\n[exit {code}]", phase="end", execution_id=eid)
                        self.registry.remove(eid)
                        summary = (
                            f"命令已停止 exit={code}（wait 预算 {int(wait_sec)}s 到期）"
                            + (f"\n{full_logs.strip()}" if full_logs.strip() else "")
                        )
                        return {
                            "summary": summary[:4000],
                            "sources": [],
                            "exit_code": code,
                            "execution_id": eid,
                            "stdout": full_logs,
                            "running": False,
                            "checkpoint": False,
                            "stopped": True,
                            "elapsed_sec": round(elapsed, 1),
                            "wait_exceeded": True,
                        }

                    tail = full_logs.strip()
                    summary = (
                        f"仍在运行（已 {int(elapsed)}s），execution_id={eid}。"
                        f"本段 wait 预算 {int(wait_sec)}s 已用尽，请审查进度后决定续接、"
                        f"wait_until_done 或 sandbox_stop。"
                    )
                    if tail:
                        summary += f"\n{tail[-3500:]}"
                    return {
                        "summary": summary[:4000],
                        "sources": [],
                        "execution_id": eid,
                        "stdout": full_logs,
                        "running": True,
                        "checkpoint": True,
                        "wait_exceeded": True,
                        "elapsed_sec": round(elapsed, 1),
                        "wait_sec": wait_sec,
                    }

                await asyncio.sleep(self.poll_interval_sec)
        except asyncio.CancelledError:
            await runtime.interrupt(eid)
            raise

    async def stop(
        self,
        runtime: SandboxRuntime,
        execution_id: str,
    ) -> dict:
        eid = (execution_id or "").strip()
        if not eid:
            return {
                "summary": "缺少 execution_id",
                "sources": [],
                "error": "missing execution_id",
            }
        rec = self.registry.get(eid)
        cursor = rec.log_cursor if rec else None
        full_logs = rec.accumulated_logs if rec else ""

        await runtime.interrupt(eid)
        final = await runtime.poll_job(eid, log_cursor=cursor)
        tail = final.logs or ""
        if tail:
            full_logs += tail
            self._emit(ensure_line_chunk(tail), phase="log", execution_id=eid)
        code = final.exit_code if final.exit_code is not None else -1
        self._emit(f"\n[exit {code}]", phase="end", execution_id=eid)
        self.registry.remove(eid)
        summary = f"已停止 execution_id={eid} exit={code}"
        if full_logs.strip():
            summary += f"\n{full_logs.strip()[-3500:]}"
        return {
            "summary": summary[:4000],
            "sources": [],
            "execution_id": eid,
            "exit_code": code,
            "stdout": full_logs,
            "running": False,
            "stopped": True,
        }


__all__ = ["SandboxExecutionEngine", "VALID_IF_EXCEEDED"]
