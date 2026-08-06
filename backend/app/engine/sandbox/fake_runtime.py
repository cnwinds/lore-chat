"""内存 FakeRuntime：单测与无 OpenSandbox 时的替代实现。"""

from __future__ import annotations

import asyncio
import shlex
import uuid
from pathlib import PurePosixPath

from app.engine.sandbox.protocol import CommandResult, DirEntry, JobStatus


class FakeSandboxRuntime:
    def __init__(self) -> None:
        self.sandbox_id = "fake-sandbox"
        self._files: dict[str, bytes] = {"/workspace/.keep": b""}
        self._jobs: dict[str, JobStatus] = {}

    async def ensure_ready(self) -> str:
        return self.sandbox_id

    def _norm(self, path: str) -> str:
        p = PurePosixPath(path if path.startswith("/") else f"/workspace/{path}")
        return str(p)

    async def run(
        self,
        command: str,
        *,
        cwd: str = "/workspace",
        timeout_sec: float | None = 120,
    ) -> CommandResult:
        del timeout_sec
        # 支持简单 && 链式
        if "&&" in command:
            stdout_all = ""
            stderr_all = ""
            code = 0
            for part in command.split("&&"):
                r = await self.run(part.strip(), cwd=cwd)
                stdout_all += r.stdout
                stderr_all += r.stderr
                code = r.exit_code
                if code != 0:
                    break
            return CommandResult(stdout=stdout_all, stderr=stderr_all, exit_code=code)

        cwd_n = self._norm(cwd)
        parts = shlex.split(command)
        if not parts:
            return CommandResult(exit_code=0)
        if parts[0] == "echo":
            # echo foo > /workspace/x or echo foo
            if ">" in parts:
                idx = parts.index(">")
                text = " ".join(parts[1:idx]) + "\n"
                target = parts[idx + 1] if idx + 1 < len(parts) else ""
                self._files[self._norm(target)] = text.encode()
                return CommandResult(stdout=text, exit_code=0)
            text = " ".join(parts[1:]) + "\n"
            return CommandResult(stdout=text, exit_code=0)
        if parts[0] == "mkdir" and "-p" in parts:
            for p in parts[2:]:
                d = self._norm(p)
                self._files[d.rstrip("/") + "/.keep"] = b""
            return CommandResult(exit_code=0)
        if parts[0] == "cat" and len(parts) >= 2:
            path = self._norm(parts[1] if parts[1].startswith("/") else f"{cwd_n}/{parts[1]}")
            data = self._files.get(path)
            if data is None:
                return CommandResult(stderr=f"cat: {path}: No such file\n", exit_code=1)
            return CommandResult(stdout=data.decode("utf-8", errors="replace"), exit_code=0)
        if parts[0] == "ls":
            # ls -1Ap -- /path
            path_arg = cwd_n
            for i, p in enumerate(parts):
                if p == "--" and i + 1 < len(parts):
                    path_arg = parts[i + 1]
                    break
                if p.startswith("/") and i > 0:
                    path_arg = p
            path = self._norm(path_arg)
            names = sorted(
                {
                    PurePosixPath(k).relative_to(path).parts[0]
                    for k in self._files
                    if k.startswith(path.rstrip("/") + "/")
                }
            )
            lines = []
            for n in names:
                if not n or n == ".keep":
                    continue
                # directory if any nested
                is_dir = any(
                    k.startswith(f"{path.rstrip('/')}/{n}/") for k in self._files
                )
                lines.append(n + ("/" if is_dir else ""))
            out = "\n".join(lines) + ("\n" if lines else "")
            return CommandResult(stdout=out, exit_code=0)
        if parts[0] == "touch" and len(parts) >= 2:
            path = self._norm(parts[1])
            self._files.setdefault(path, b"")
            return CommandResult(exit_code=0)
        if parts[0] == "head" and "-c" in parts:
            # head -c N -- path
            try:
                n_idx = parts.index("-c")
                nbytes = int(parts[n_idx + 1])
                path = parts[-1]
            except (ValueError, IndexError):
                return CommandResult(stderr="bad head\n", exit_code=1)
            data = self._files.get(self._norm(path))
            if data is None:
                return CommandResult(stderr="missing\n", exit_code=1)
            return CommandResult(
                stdout=data[:nbytes].decode("utf-8", errors="replace"),
                exit_code=0,
            )
        return CommandResult(stdout=f"ran:{command}\n", exit_code=0)

    async def start_job(self, command: str, *, cwd: str = "/workspace") -> str:
        eid = uuid.uuid4().hex
        self._jobs[eid] = JobStatus(execution_id=eid, running=True, logs="")

        async def _finish() -> None:
            await asyncio.sleep(0.05)
            if eid not in self._jobs:
                return
            if self._jobs[eid].exit_code == -1 and not self._jobs[eid].running:
                return  # interrupted
            result = await self.run(command, cwd=cwd)
            cur = self._jobs.get(eid)
            if cur is None or not cur.running:
                return
            self._jobs[eid] = JobStatus(
                execution_id=eid,
                running=False,
                exit_code=result.exit_code,
                logs=(result.stdout or "") + (result.stderr or ""),
            )

        asyncio.create_task(_finish())
        return eid

    async def poll_job(
        self, execution_id: str, *, log_cursor: int | None = None
    ) -> JobStatus:
        st = self._jobs.get(execution_id)
        if st is None:
            return JobStatus(
                execution_id=execution_id,
                running=False,
                exit_code=1,
                logs="unknown job",
                next_cursor=0,
            )
        cursor = int(log_cursor or 0)
        logs = st.logs[cursor:]
        return JobStatus(
            execution_id=st.execution_id,
            running=st.running,
            exit_code=st.exit_code,
            logs=logs,
            next_cursor=cursor + len(logs),
        )

    async def interrupt(self, execution_id: str) -> None:
        st = self._jobs.get(execution_id)
        if st is None:
            return
        self._jobs[execution_id] = JobStatus(
            execution_id=execution_id,
            running=False,
            exit_code=-1,
            logs=(st.logs or "") + "\n[interrupted]\n",
        )

    async def interrupt_all(self) -> None:
        for eid, st in list(self._jobs.items()):
            if st.running:
                await self.interrupt(eid)

    async def list_dir(self, path: str = "/workspace") -> list[DirEntry]:
        path_n = self._norm(path).rstrip("/")
        prefix = path_n + "/"
        names: dict[str, bool] = {}
        for k in self._files:
            if not k.startswith(prefix):
                continue
            rest = k[len(prefix) :]
            if not rest:
                continue
            first = rest.split("/", 1)[0]
            if first == ".keep":
                continue
            is_dir = "/" in rest
            names[first] = names.get(first, False) or is_dir
        return [
            DirEntry(name=n, path=f"{path_n}/{n}", is_dir=names[n])
            for n in sorted(names)
        ]

    async def read_file(self, path: str, *, max_bytes: int = 200_000) -> bytes:
        data = self._files.get(self._norm(path))
        if data is None:
            raise FileNotFoundError(path)
        return data[:max_bytes]

    async def write_file(self, path: str, data: bytes) -> None:
        self._files[self._norm(path)] = data
