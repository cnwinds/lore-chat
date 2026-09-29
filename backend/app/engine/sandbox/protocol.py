"""Sandbox Runtime 协议与共享类型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class CommandResult:
    """命令结果。``output`` 为 stdout/stderr 合流，逐字节等于命令实际写出的文本。"""

    output: str = ""
    exit_code: int = 0
    execution_id: str | None = None
    timed_out: bool = False


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


class SandboxFsError(Exception):
    """沙箱文件观测失败；``kind`` 区分「不存在」与其它失败，禁止混用。"""

    kind = "runtime_error"

    def __init__(self, path: str, detail: str = "") -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"{self.kind}: {path}" + (f" ({detail})" if detail else ""))

    def describe(self) -> str:
        return f"沙箱执行异常，未能确认路径状态：{self.path}" + (
            f"；{self.detail}" if self.detail else ""
        )


class SandboxNotFound(SandboxFsError):
    kind = "not_found"

    def describe(self) -> str:
        return f"此刻不存在：{self.path}"


class SandboxNotADirectory(SandboxFsError):
    kind = "not_a_directory"

    def describe(self) -> str:
        return f"不是目录：{self.path}"


class SandboxPermissionDenied(SandboxFsError):
    kind = "permission_denied"

    def describe(self) -> str:
        return f"无权限访问：{self.path}"


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
        """失败抛 ``SandboxFsError`` 子类。"""
        ...

    async def read_file(self, path: str, *, max_bytes: int = 200_000) -> bytes:
        """失败抛 ``SandboxFsError`` 子类。"""
        ...

    async def write_file(self, path: str, data: bytes) -> None:
        ...

    async def write_files(self, entries: list[tuple[str, bytes]]) -> None:
        """批量写入沙箱文件（path, data）；空列表为 no-op。"""
        ...

    async def destroy_container(self, *, keep_volume: bool = True) -> None:
        """销毁执行容器；keep_volume=True 时保留 PVC / 工作区数据。"""
        ...
