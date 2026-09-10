"""沙箱 execution 元数据：跨 sandbox_run 续接时的 cursor 与日志累积。"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class ExecutionRecord:
    execution_id: str
    command: str
    cwd: str
    started_at: float
    log_cursor: int | None = None
    accumulated_logs: str = ""
    role_id: str | None = None
    conversation_id: str | None = None
    schedule_id: str | None = None


class ExecutionRegistry:
    """进程内 execution 登记；沙箱 job 本身由 runtime 持有。"""

    def __init__(self) -> None:
        self._records: dict[str, ExecutionRecord] = {}

    def register(
        self,
        execution_id: str,
        command: str,
        *,
        cwd: str,
        role_id: str | None = None,
        conversation_id: str | None = None,
        schedule_id: str | None = None,
    ) -> ExecutionRecord:
        rec = ExecutionRecord(
            execution_id=execution_id,
            command=command,
            cwd=cwd,
            started_at=time.monotonic(),
            role_id=role_id,
            conversation_id=conversation_id,
            schedule_id=schedule_id,
        )
        self._records[execution_id] = rec
        return rec

    def get(self, execution_id: str) -> ExecutionRecord | None:
        return self._records.get(execution_id)

    def find(
        self,
        *,
        conversation_id: str | None = None,
        role_id: str | None = None,
    ) -> list[ExecutionRecord]:
        out: list[ExecutionRecord] = []
        for rec in self._records.values():
            if conversation_id and rec.conversation_id != conversation_id:
                continue
            if role_id and rec.role_id != role_id:
                continue
            if conversation_id is None and role_id is None:
                continue
            out.append(rec)
        return out

    def update_cursor(
        self,
        execution_id: str,
        log_cursor: int | None,
        accumulated_logs: str,
    ) -> None:
        rec = self._records.get(execution_id)
        if rec is None:
            return
        rec.log_cursor = log_cursor
        rec.accumulated_logs = accumulated_logs

    def elapsed_sec(self, execution_id: str) -> float:
        rec = self._records.get(execution_id)
        if rec is None:
            return 0.0
        return max(0.0, time.monotonic() - rec.started_at)

    def remove(self, execution_id: str) -> None:
        self._records.pop(execution_id, None)


__all__ = ["ExecutionRecord", "ExecutionRegistry"]
