"""Sandbox Runtime 协议与共享类型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class CommandResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_id: str | None = None


@dataclass
class JobStatus:
    execution_id: str
    running: bool
    exit_code: int | None = None
    logs: str = ""
    # OpenSandbox EXECD-COMMANDS-TAIL-CURSOR；Fake 用字符偏移
    next_cursor: int | None = None


@dataclass
class DirEntry:
    name: str
    path: str
    is_dir: bool


class SandboxRuntime(Protocol):
    """Agent 可调用的执行环境（OpenSandbox 或 Fake）。"""

    async def ensure_ready(self) -> str:
        """确保沙箱可用，返回 sandbox_id。"""
        ...

    async def run(
        self,
        command: str,
        *,
        cwd: str = "/workspace",
        timeout_sec: float | None = 120,
    ) -> CommandResult:
        ...

    async def start_job(
        self,
        command: str,
        *,
        cwd: str = "/workspace",
    ) -> str:
        """后台启动命令，返回 execution_id。"""
        ...

    async def poll_job(self, execution_id: str, *, log_cursor: int | None = None) -> JobStatus:
        ...

    async def interrupt(self, execution_id: str) -> None:
        """中断指定执行（尽量 SIGTERM）。"""
        ...

    async def interrupt_all(self) -> None:
        """中断本 runtime 跟踪中的全部执行。"""
        ...

    async def list_dir(self, path: str = "/workspace") -> list[DirEntry]:
        ...

    async def read_file(self, path: str, *, max_bytes: int = 200_000) -> bytes:
        ...

    async def write_file(self, path: str, data: bytes) -> None:
        ...
