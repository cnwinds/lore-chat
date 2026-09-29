"""内存 FakeRuntime：单测与无 OpenSandbox 时的替代实现。"""

from __future__ import annotations

import asyncio
import errno
import json
import shlex
import time
import uuid
from pathlib import PurePosixPath

from app.engine.sandbox import probes
from app.engine.sandbox.protocol import (
    CommandResult,
    DirEntry,
    JobStatus,
    SandboxFsError,
    SandboxNotFound,
)


class FakeSandboxRuntime:
    def __init__(self, *, sandbox_id: str | None = None, role_id: str | None = None) -> None:
        self.sandbox_id = sandbox_id or "fake-sandbox"
        self.role_id = role_id
        self._files: dict[str, bytes] = {"/workspace/.keep": b""}
        self._mtimes: dict[str, float] = {}
        self._jobs: dict[str, JobStatus] = {}
        self.last_cwd: str | None = None
        self._active_executions: set[str] = set()
        self.container_alive = True
        self.destroy_calls: list[dict] = []

    async def ensure_ready(self) -> str:
        if not self.container_alive:
            self.container_alive = True
            base = (self.sandbox_id or "fake").rsplit("-recreated", 1)[0]
            self.sandbox_id = f"{base}-recreated"
        return self.sandbox_id

    def _norm(self, path: str) -> str:
        p = PurePosixPath(path if path.startswith("/") else f"/workspace/{path}")
        return str(p)

    def _put(self, path_n: str, data: bytes) -> None:
        self._files[path_n] = data
        self._mtimes[path_n] = time.time()

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
            output_all = ""
            code = 0
            for part in command.split("&&"):
                r = await self.run(part.strip(), cwd=cwd)
                output_all += r.output
                code = r.exit_code
                if code != 0:
                    break
            return CommandResult(output=output_all, exit_code=code)

        parts = shlex.split(command)
        if not parts:
            return CommandResult(exit_code=0)
        # 探针是引擎内部命令，不记入 last_cwd（测试用它断言用户命令的工作目录）
        if parts[:3] == ["python3", "-c", probes.LIST_DIR_SCRIPT] and len(parts) == 4:
            return CommandResult(output=self._probe_list_dir(parts[3]), exit_code=0)
        if parts[:3] == ["python3", "-c", probes.WORKSPACE_OUTPUTS_SCRIPT] and len(parts) == 4:
            return CommandResult(
                output=self._probe_workspace_outputs(json.loads(parts[3])), exit_code=0
            )
        self.last_cwd = cwd
        cwd_n = self._norm(cwd)
        if parts[0] == "echo":
            # echo foo > /workspace/x or echo foo
            if ">" in parts:
                idx = parts.index(">")
                text = " ".join(parts[1:idx]) + "\n"
                target = parts[idx + 1] if idx + 1 < len(parts) else ""
                self._put(self._norm(target), text.encode())
                return CommandResult(output=text, exit_code=0)
            text = " ".join(parts[1:]) + "\n"
            return CommandResult(output=text, exit_code=0)
        if parts[0] == "rm" and "-rf" in parts:
            for p in parts[1:]:
                if p in ("-rf", "--"):
                    continue
                d = self._norm(p).rstrip("/")
                for k in [k for k in self._files if k == d or k.startswith(d + "/")]:
                    del self._files[k]
            return CommandResult(exit_code=0)
        if parts[0] == "mkdir" and "-p" in parts:
            for p in parts[2:]:
                d = self._norm(p)
                self._files[d.rstrip("/") + "/.keep"] = b""
            return CommandResult(exit_code=0)
        if parts[0] == "cat" and len(parts) >= 2:
            path = self._norm(parts[1] if parts[1].startswith("/") else f"{cwd_n}/{parts[1]}")
            data = self._files.get(path)
            if data is None:
                return CommandResult(output=f"cat: {path}: No such file\n", exit_code=1)
            return CommandResult(output=data.decode("utf-8", errors="replace"), exit_code=0)
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
            return CommandResult(output=out, exit_code=0)
        if parts[0] == "touch" and len(parts) >= 2:
            path = self._norm(parts[1])
            self._put(path, self._files.get(path, b""))
            return CommandResult(exit_code=0)
        if parts[0] == "head" and "-c" in parts:
            # head -c N -- path
            try:
                n_idx = parts.index("-c")
                nbytes = int(parts[n_idx + 1])
                path = parts[-1]
            except (ValueError, IndexError):
                return CommandResult(output="bad head\n", exit_code=1)
            data = self._files.get(self._norm(path))
            if data is None:
                return CommandResult(output="missing\n", exit_code=1)
            return CommandResult(
                output=data[:nbytes].decode("utf-8", errors="replace"),
                exit_code=0,
            )
        return CommandResult(output=f"ran:{command}\n", exit_code=0)

    async def start_job(self, command: str, *, cwd: str = "/workspace") -> str:
        eid = uuid.uuid4().hex
        self.last_cwd = cwd
        self._jobs[eid] = JobStatus(execution_id=eid, running=True, logs="")
        self._active_executions.add(eid)

        async def _finish() -> None:
            if command.strip() == "__stream_echo__":
                for i in range(5):
                    await asyncio.sleep(0.08)
                    st = self._jobs.get(eid)
                    if st is None or not st.running:
                        return
                    self._jobs[eid] = JobStatus(
                        execution_id=eid,
                        running=True,
                        exit_code=0,
                        logs=(st.logs or "") + f"line{i}\n",
                    )
                st = self._jobs.get(eid)
                if st is None or not st.running:
                    return
                self._jobs[eid] = JobStatus(
                    execution_id=eid,
                    running=False,
                    exit_code=0,
                    logs=st.logs or "",
                )
                return
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
                logs=result.output or "",
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
        if not st.running:
            self._active_executions.discard(execution_id)
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
        self._active_executions.discard(execution_id)

    async def interrupt_all(self) -> None:
        for eid, st in list(self._jobs.items()):
            if st.running:
                await self.interrupt(eid)

    def _kind(self, path_n: str) -> str | None:
        if path_n in self._files:
            return "file"
        prefix = path_n.rstrip("/") + "/"
        if any(k.startswith(prefix) for k in self._files):
            return "dir"
        return None

    def _probe_list_dir(self, path: str) -> str:
        """模拟探针在真实沙箱里的原始输出，由共用解码器解析。"""
        path_n = self._norm(path).rstrip("/") or "/"
        kind = self._kind(path_n)
        if kind is None:
            return probes.probe_line(
                {"ok": False, "errno": errno.ENOENT, "detail": "No such file or directory"}
            )
        if kind == "file":
            return probes.probe_line(
                {"ok": False, "errno": errno.ENOTDIR, "detail": "Not a directory"}
            )
        prefix = path_n.rstrip("/") + "/"
        names: dict[str, bool] = {}
        for k in self._files:
            if not k.startswith(prefix):
                continue
            rest = k[len(prefix) :]
            first = rest.split("/", 1)[0]
            if not first or first == ".keep":
                continue
            names[first] = names.get(first, False) or "/" in rest
        return probes.probe_line(
            {
                "ok": True,
                "entries": [{"name": n, "is_dir": d} for n, d in names.items()],
            }
        )

    def _probe_workspace_outputs(self, cfg: dict) -> str:
        root = cfg["root"].rstrip("/")
        since = time.time() - float(cfg["age"])
        own = {"conversations": cfg.get("conv"), "schedules": cfg.get("sched")}
        skip = set(cfg.get("skip") or [])
        hits: list[tuple[float, str, int]] = []
        for path, data in self._files.items():
            if not path.startswith(root + "/"):
                continue
            segs = path[len(root) + 1 :].split("/")
            dirs, name = segs[:-1], segs[-1]
            if name.startswith(".") or any(d.startswith(".") or d in skip for d in dirs):
                continue
            if len(dirs) >= 2 and dirs[0] in own and dirs[1] != own[dirs[0]]:
                continue
            mtime = self._mtimes.get(path, 0.0)
            if mtime >= since:
                hits.append((mtime, path, len(data)))
        hits.sort(reverse=True)
        limit = int(cfg["limit"])
        return probes.probe_line(
            {
                "ok": True,
                "files": [{"path": p, "size": s} for _, p, s in hits[:limit]],
                "truncated": len(hits) > limit,
            }
        )

    async def list_dir(self, path: str = "/workspace") -> list[DirEntry]:
        result = await self.run(probes.list_dir_command(path), cwd="/")
        return probes.decode_list_dir(path, result)

    async def read_file(self, path: str, *, max_bytes: int = 200_000) -> bytes:
        path_n = self._norm(path)
        kind = self._kind(path_n)
        if kind is None:
            raise SandboxNotFound(path)
        if kind == "dir":
            raise SandboxFsError(path, "is a directory")
        return self._files[path_n][:max_bytes]

    async def write_file(self, path: str, data: bytes) -> None:
        self._put(self._norm(path), data)

    async def write_files(self, entries: list[tuple[str, bytes]]) -> None:
        for path, data in entries:
            await self.write_file(path, data)

    async def destroy_container(self, *, keep_volume: bool = True) -> None:
        await self.interrupt_all()
        self.container_alive = False
        self.destroy_calls.append({"keep_volume": keep_volume})
        self._jobs.clear()
        self._active_executions.clear()
        if not keep_volume:
            self._files = {"/workspace/.keep": b""}
