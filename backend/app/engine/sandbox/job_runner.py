"""沙箱长任务等待：poll / progress / timeout / interrupt。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from app.engine.chat.progress_log import ensure_line_chunk
from app.engine.sandbox.progress import emit_progress
from app.engine.sandbox.protocol import SandboxRuntime

ProgressEmit = Callable[..., None]


class SandboxJobRunner:
    def __init__(
        self,
        *,
        poll_interval_sec: float = 0.5,
        max_wait_sec: float = 600,
        emit: ProgressEmit | None = None,
    ) -> None:
        self.poll_interval_sec = poll_interval_sec
        self.max_wait_sec = max_wait_sec
        self._emit = emit or emit_progress

    async def wait(
        self,
        runtime: SandboxRuntime,
        command: str,
        *,
        cwd: str = "/workspace",
    ) -> dict:
        eid = await runtime.start_job(command, cwd=cwd)
        self._emit(f"job started id={eid}\n", phase="job", execution_id=eid)
        cursor: int | None = None
        waited = 0.0
        full_logs = ""
        try:
            while waited < self.max_wait_sec:
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
                if not status.running:
                    code = status.exit_code if status.exit_code is not None else 0
                    self._emit(f"\n[exit {code}]", phase="end", execution_id=eid)
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
                    }
                    if code != 0:
                        out["error"] = f"exit_code={code}"
                    return out
                await asyncio.sleep(self.poll_interval_sec)
                waited += self.poll_interval_sec
        except asyncio.CancelledError:
            await runtime.interrupt(eid)
            raise
        return {
            "summary": (
                f"命令仍在运行（已等待 {int(waited)}s），execution_id={eid}。"
                f"可用 sandbox_job_status 稍后查询。"
            ),
            "sources": [],
            "execution_id": eid,
            "running": True,
            "error": "job timeout waiting",
        }


__all__ = ["SandboxJobRunner"]
