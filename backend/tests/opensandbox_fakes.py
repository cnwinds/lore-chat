"""OpenSandbox SDK 的最小替身：后台 job + 游标日志，按真实 execd 的分页语义回放输出。"""

from __future__ import annotations

from types import SimpleNamespace


class FakeJobCommands:
    """``commands`` 替身。``scripts`` 把命令映射为日志分页（每次 poll 吐一页）。

    未登记的命令输出为空、退出码 0。``exit_codes`` 可覆盖退出码。
    """

    def __init__(
        self,
        scripts: dict[str, list[str]] | None = None,
        *,
        exit_codes: dict[str, int] | None = None,
        running_forever: set[str] | None = None,
    ) -> None:
        self.scripts = dict(scripts or {})
        self.exit_codes = dict(exit_codes or {})
        self.running_forever = set(running_forever or ())
        self.started: list[dict] = []
        self.interrupted: list[str] = []
        self._jobs: dict[str, dict] = {}

    async def run(self, command: str, *, opts=None, handlers=None):
        assert getattr(opts, "background", False), "只允许后台 job 通道"
        eid = f"e{len(self.started) + 1}"
        self.started.append({"id": eid, "command": command, "cwd": opts.working_directory})
        self._jobs[eid] = {
            "pages": list(self.scripts.get(command, [])),
            "code": self.exit_codes.get(command, 0),
            "forever": command in self.running_forever,
        }
        return SimpleNamespace(id=eid)

    async def get_command_status(self, execution_id: str):
        job = self._jobs[execution_id]
        running = bool(job["pages"]) or job["forever"]
        return SimpleNamespace(
            running=running,
            exit_code=None if running else job["code"],
        )

    async def get_background_command_logs(self, execution_id: str, cursor=None):
        job = self._jobs[execution_id]
        cur = int(cursor or 0)
        content = job["pages"].pop(0) if job["pages"] else ""
        return SimpleNamespace(content=content, cursor=cur + len(content))

    async def interrupt(self, execution_id: str) -> None:
        self.interrupted.append(execution_id)
        job = self._jobs.get(execution_id)
        if job is not None:
            job["forever"] = False
            job["pages"] = []
            job["code"] = 137


class LocalShellCommands(FakeJobCommands):
    """在本机 bash 真跑命令，再按 ``page_size`` 字节切页回放（故意切断行）。"""

    def __init__(self, *, page_size: int = 7) -> None:
        super().__init__()
        self.page_size = page_size

    async def run(self, command: str, *, opts=None, handlers=None):
        import subprocess

        assert getattr(opts, "background", False), "只允许后台 job 通道"
        proc = subprocess.run(
            ["bash", "-c", command],
            cwd=opts.working_directory or "/",
            capture_output=True,
            check=False,
        )
        text = (proc.stdout + proc.stderr).decode("utf-8", errors="surrogateescape")
        n = self.page_size
        self.scripts[command] = [text[i : i + n] for i in range(0, len(text), n)]
        self.exit_codes[command] = proc.returncode
        return await super().run(command, opts=opts, handlers=handlers)


class LocalFiles:
    """``files`` 替身：读写本机路径，缺失时抛与 execd 同形的 FILE_NOT_FOUND。"""

    async def read_bytes(self, path: str, **kw) -> bytes:
        from pathlib import Path

        p = Path(path)
        if not p.exists():
            raise sdk_api_error(
                "FILE_NOT_FOUND",
                f"file not found. open {path}: no such file or directory",
                status=404,
            )
        data = p.read_bytes()
        rh = kw.get("range_header")
        if isinstance(rh, str) and rh.startswith("bytes="):
            start_s, _, end_s = rh.removeprefix("bytes=").partition("-")
            return data[int(start_s or 0) : int(end_s) + 1 if end_s else len(data)]
        return data

    async def write_files(self, entries) -> None:
        from pathlib import Path

        for e in entries:
            p = Path(e.path)
            p.parent.mkdir(parents=True, exist_ok=True)
            raw = e.data.encode("utf-8") if isinstance(e.data, str) else bytes(e.data)
            p.write_bytes(raw)


def local_shell_sandbox(*, page_size: int = 7) -> SimpleNamespace:
    return SimpleNamespace(
        id="local-sb",
        sandbox_id="local-sb",
        commands=LocalShellCommands(page_size=page_size),
        files=LocalFiles(),
    )


def sdk_api_error(code: str, message: str, *, status: int | None = None) -> Exception:
    """构造与 ``SandboxApiException`` 同形的异常（``.error.code`` / ``.error.message``）。"""

    class SandboxApiException(Exception):
        pass

    exc = SandboxApiException(f"API error: HTTP {status}: {message} | [{code}] {message}")
    exc.error = SimpleNamespace(code=code, message=message)
    exc.status_code = status
    return exc
