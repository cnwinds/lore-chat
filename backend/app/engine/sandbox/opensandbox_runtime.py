"""OpenSandbox 实现的 SandboxRuntime。"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import shlex
import socket
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from app.engine.sandbox import state as sandbox_state
from app.engine.sandbox.mirrors import (
    MirrorRegion,
    apt_configure_script,
    mirror_env,
    normalize_mirror_region,
)
from app.engine.sandbox.protocol import CommandResult, DirEntry, JobStatus

_log = logging.getLogger(__name__)

_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


def _host_gateway_ip() -> str:
    try:
        return socket.gethostbyname("host.docker.internal")
    except OSError:
        return "172.17.0.1"


def _rewrite_proxy_host_for_sandbox(url: str, gateway: str) -> str:
    """沙箱在 docker bridge 上通常解析不了 host.docker.internal，改写为网关 IP。"""
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    if not parsed.hostname:
        return url
    host = parsed.hostname.lower()
    if host in ("host.docker.internal", "localhost", "127.0.0.1"):
        netloc = gateway
        if parsed.port:
            netloc = f"{gateway}:{parsed.port}"
        if parsed.username:
            auth = parsed.username
            if parsed.password:
                auth = f"{auth}:{parsed.password}"
            netloc = f"{auth}@{netloc}"
        return urlunparse(parsed._replace(netloc=netloc))
    return url


def sandbox_proxy_env_from_host() -> dict[str, str]:
    """从当前进程环境构造注入沙箱的代理变量。"""
    gateway = _host_gateway_ip()
    out: dict[str, str] = {}
    for key in _PROXY_ENV_KEYS:
        raw = os.environ.get(key)
        if not raw or not str(raw).strip():
            continue
        val = str(raw).strip()
        if key.lower() in ("no_proxy",):
            # 确保网关与常见内网不走代理
            parts = [p.strip() for p in val.split(",") if p.strip()]
            for extra in (gateway, "172.17.0.1", "localhost", "127.0.0.1"):
                if extra not in parts:
                    parts.append(extra)
            out[key] = ",".join(parts)
        else:
            out[key] = _rewrite_proxy_host_for_sandbox(val, gateway)
    return out


class OpenSandboxRuntime:
    def __init__(
        self,
        *,
        kb_path: Path,
        domain: str,
        protocol: str = "http",
        api_key: str | None = None,
        use_server_proxy: bool = True,
        workspace_volume: str = "lorechat-sandbox-workspace",
        image: str = "lorechat-sandbox-agent:local",
        sandbox_env: dict[str, str] | None = None,
        mirror_region: MirrorRegion = "cn",
    ) -> None:
        self.kb_path = Path(kb_path)
        self.domain = domain
        self.protocol = protocol
        self.api_key = api_key
        self.use_server_proxy = use_server_proxy
        self.workspace_volume = workspace_volume
        self.image = image
        self.sandbox_env = dict(sandbox_env or {})
        self.mirror_region: MirrorRegion = normalize_mirror_region(mirror_region)
        self._sandbox = None
        self._sandbox_id: str | None = None
        self._applying_mirrors = False
        self._active_executions: set[str] = set()

    @staticmethod
    def _is_recoverable_sandbox_error(exc: BaseException) -> bool:
        if isinstance(exc, asyncio.CancelledError):
            return False
        name = type(exc).__name__
        if name in ("ConnectError", "ConnectTimeout", "ReadError", "WriteError"):
            return True
        mod = type(exc).__module__ or ""
        if ("httpx" in mod or "httpcore" in mod) and (
            "Connect" in name or "Timeout" in name
        ):
            return True
        text = str(exc).lower()
        if "sandbox_not_found" in text or "connection attempts failed" in text:
            return True
        if "sandboxapiexception" in name.lower() or "not found" in text:
            return True
        return False

    def _invalidate_sandbox(self, *, clear_persisted: bool) -> None:
        self._sandbox = None
        self._sandbox_id = None
        if clear_persisted:
            sandbox_state.clear_sandbox_id(self.kb_path)

    async def _probe_sandbox(self) -> bool:
        if self._sandbox is None or not self._sandbox_id:
            return False
        commands = getattr(self._sandbox, "commands", None)
        if commands is None or not callable(getattr(commands, "run", None)):
            return True
        from opensandbox.models.execd import RunCommandOpts

        try:
            opts = RunCommandOpts(
                working_directory="/",
                background=False,
                timeout=timedelta(seconds=15),
            )
            await self._sandbox.commands.run("true", opts=opts)
            return True
        except Exception as exc:
            if self._is_recoverable_sandbox_error(exc):
                return False
            raise

    async def _call_sandbox(self, fn):
        """执行一次沙箱 API 调用；连接类失败时清缓存并重建后重试一次。"""
        last_exc: BaseException | None = None
        for attempt in (1, 2):
            await self.ensure_ready()
            assert self._sandbox is not None
            try:
                return await fn(self._sandbox)
            except Exception as exc:
                last_exc = exc
                if attempt == 1 and self._is_recoverable_sandbox_error(exc):
                    _log.warning(
                        "sandbox session stale (attempt %s), recreating",
                        attempt,
                        exc_info=True,
                    )
                    self._invalidate_sandbox(clear_persisted=True)
                    continue
                raise
        assert last_exc is not None
        raise last_exc

    def _connection_config(self):
        from opensandbox.config import ConnectionConfig

        return ConnectionConfig(
            domain=self.domain,
            protocol=self.protocol,
            api_key=self.api_key,
            use_server_proxy=self.use_server_proxy,
            request_timeout=timedelta(seconds=60),
        )

    async def ensure_ready(self) -> str:
        if self._sandbox is not None and self._sandbox_id:
            if await self._probe_sandbox():
                if not self._applying_mirrors:
                    await self._ensure_mirrors()
                return self._sandbox_id
            _log.warning(
                "sandbox %s no longer reachable; recreating",
                self._sandbox_id,
            )
            self._invalidate_sandbox(clear_persisted=True)

        from opensandbox import Sandbox
        from opensandbox.models.sandboxes import PVC, Volume

        # Volume 由 OpenSandbox PVC(create_if_not_exists=True) 在控制面创建；
        # backend 无 docker CLI / docker.sock，禁止本机 docker volume create。
        config = self._connection_config()
        existing = sandbox_state.load_sandbox_id(self.kb_path)
        if existing:
            try:
                self._sandbox = await Sandbox.connect(
                    existing, connection_config=config
                )
                self._sandbox_id = existing
                _log.info("reconnected sandbox id=%s", existing)
                await self._ensure_mirrors()
                return existing
            except Exception:
                _log.warning(
                    "reconnect sandbox %s failed; creating new",
                    existing,
                    exc_info=True,
                )
                self._invalidate_sandbox(clear_persisted=True)

        create_env = {**self.sandbox_env, **mirror_env(self.mirror_region)}
        sandbox = await Sandbox.create(
            self.image,
            connection_config=config,
            timeout=timedelta(hours=24),
            ready_timeout=timedelta(minutes=3),
            env=create_env or None,
            volumes=[
                Volume(
                    name="workspace",
                    pvc=PVC(claim_name=self.workspace_volume),
                    mount_path="/workspace",
                    read_only=False,
                )
            ],
        )
        sid = getattr(sandbox, "id", None) or getattr(sandbox, "sandbox_id", None)
        if not sid:
            raise RuntimeError("OpenSandbox create returned no sandbox id")
        self._sandbox = sandbox
        self._sandbox_id = str(sid)
        sandbox_state.save_state(self.kb_path, sandbox_id=self._sandbox_id)
        # 确保工作区存在（跳过 ensure_ready 递归）
        await self.run("mkdir -p /workspace", cwd="/", timeout_sec=30, _ready=False)
        await self._ensure_mirrors(force=True)
        _log.info(
            "created sandbox id=%s mirror=%s",
            self._sandbox_id,
            self.mirror_region,
        )
        return self._sandbox_id

    async def _ensure_mirrors(self, *, force: bool = False) -> None:
        """按当前 mirror_region 配置 apt/pip/npm；区域变化时重配。"""
        import base64

        if self._sandbox is None or not self._sandbox_id:
            return
        applied = sandbox_state.load_mirror_region(self.kb_path)
        if not force and applied == self.mirror_region:
            return
        script = apt_configure_script(self.mirror_region)
        payload = base64.b64encode(script.encode("utf-8")).decode("ascii")
        self._applying_mirrors = True
        try:
            result = await self.run(
                f"echo {payload} | base64 -d | bash",
                cwd="/",
                timeout_sec=60,
                _ready=False,
            )
        finally:
            self._applying_mirrors = False
        if result.exit_code != 0:
            _log.warning(
                "apply sandbox mirrors region=%s failed exit=%s stderr=%s",
                self.mirror_region,
                result.exit_code,
                (result.stderr or "")[:300],
            )
            return
        sandbox_state.save_state(
            self.kb_path,
            sandbox_id=self._sandbox_id,
            mirror_region=self.mirror_region,
        )
        _log.info("sandbox mirrors applied region=%s", self.mirror_region)

    @staticmethod
    def _stdout_text(execution) -> str:
        logs = getattr(execution, "logs", None)
        if logs is not None and getattr(logs, "stdout", None):
            return "".join(getattr(x, "text", str(x)) for x in logs.stdout)
        return ""

    @staticmethod
    def _stderr_text(execution) -> str:
        logs = getattr(execution, "logs", None)
        if logs is not None and getattr(logs, "stderr", None):
            return "".join(getattr(x, "text", str(x)) for x in logs.stderr)
        return ""

    async def run(
        self,
        command: str,
        *,
        cwd: str = "/workspace",
        timeout_sec: float | None = 120,
        _ready: bool = True,
    ) -> CommandResult:
        from opensandbox.models.execd import ExecutionHandlers, OutputMessage, RunCommandOpts

        from app.engine.chat.progress_log import ensure_line_chunk
        from app.engine.sandbox.progress import emit_progress

        async def _execute(sb) -> CommandResult:
            out_chunks: list[str] = []
            err_chunks: list[str] = []
            current_eid: dict[str, str | None] = {"id": None}

            def _track(eid: str | None) -> None:
                if not eid:
                    return
                current_eid["id"] = str(eid)
                self._active_executions.add(str(eid))

            async def on_stdout(msg: OutputMessage) -> None:
                text = msg.text or ""
                if not text:
                    return
                out_chunks.append(text)
                emit_progress(ensure_line_chunk(text))

            async def on_stderr(msg: OutputMessage) -> None:
                text = msg.text or ""
                if not text:
                    return
                err_chunks.append(text)
                emit_progress(ensure_line_chunk(text))

            async def on_init(execution) -> None:
                _track(
                    getattr(execution, "id", None)
                    or getattr(execution, "execution_id", None)
                )

            opts_kwargs: dict = {
                "working_directory": cwd or "/workspace",
                "background": False,
            }
            if timeout_sec is not None:
                opts_kwargs["timeout"] = timedelta(seconds=timeout_sec)
            opts = RunCommandOpts(**opts_kwargs)

            handlers = ExecutionHandlers(
                on_stdout=on_stdout,
                on_stderr=on_stderr,
                on_init=on_init,
            )
            execution = None
            try:
                execution = await sb.commands.run(command, opts=opts, handlers=handlers)
                _track(getattr(execution, "id", None))
            except asyncio.CancelledError:
                eid = current_eid["id"]
                if eid:
                    await self.interrupt(eid)
                raise
            finally:
                done_id = current_eid["id"]
                if done_id:
                    self._active_executions.discard(done_id)

            assert execution is not None
            stdout = "".join(out_chunks) or self._stdout_text(execution)
            stderr = "".join(err_chunks) or self._stderr_text(execution)
            exit_code = getattr(execution, "exit_code", None)
            if exit_code is None:
                exit_code = 0 if not stderr else 1
            eid = current_eid["id"] or getattr(execution, "id", None)
            return CommandResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=int(exit_code),
                execution_id=str(eid) if eid else None,
            )

        if not _ready:
            sb = self._sandbox
            if sb is None:
                raise RuntimeError("sandbox not ready")
            return await _execute(sb)

        return await self._call_sandbox(_execute)

    async def start_job(self, command: str, *, cwd: str = "/workspace") -> str:
        from opensandbox.models.execd import RunCommandOpts

        async def _start(sb) -> str:
            opts = RunCommandOpts(
                working_directory=cwd or "/workspace", background=True
            )
            execution = await sb.commands.run(command, opts=opts)
            eid = getattr(execution, "id", None)
            if not eid:
                raise RuntimeError("background command returned no execution id")
            eid_s = str(eid)
            self._active_executions.add(eid_s)
            return eid_s

        return await self._call_sandbox(_start)

    async def poll_job(
        self, execution_id: str, *, log_cursor: int | None = None
    ) -> JobStatus:
        async def _poll(sb) -> JobStatus:
            status = await sb.commands.get_command_status(execution_id)
            logs_obj = await sb.commands.get_background_command_logs(
                execution_id, cursor=log_cursor
            )
            raw = getattr(logs_obj, "content", None)
            if raw is None:
                raw = getattr(logs_obj, "output", None) or str(logs_obj)
            if not isinstance(raw, str):
                raw = str(raw)
            running = bool(getattr(status, "running", False))
            exit_code = getattr(status, "exit_code", None)
            next_cursor = getattr(logs_obj, "cursor", None)
            if not running:
                self._active_executions.discard(execution_id)
            return JobStatus(
                execution_id=execution_id,
                running=running,
                exit_code=exit_code if exit_code is None else int(exit_code),
                logs=raw,
                next_cursor=int(next_cursor) if next_cursor is not None else None,
            )

        return await self._call_sandbox(_poll)

    async def interrupt(self, execution_id: str) -> None:
        if not execution_id:
            return
        try:
            if self._sandbox is None:
                await self.ensure_ready()
            assert self._sandbox is not None
            await self._sandbox.commands.interrupt(execution_id)
        except Exception:
            _log.warning("interrupt execution %s failed", execution_id, exc_info=True)
        finally:
            self._active_executions.discard(execution_id)

    async def interrupt_all(self) -> None:
        for eid in list(self._active_executions):
            await self.interrupt(eid)

    async def list_dir(self, path: str = "/workspace") -> list[DirEntry]:
        result = await self.run(
            f"ls -1Ap -- {path}",
            cwd="/",
            timeout_sec=30,
        )
        if result.exit_code != 0:
            raise FileNotFoundError(result.stderr or path)
        entries: list[DirEntry] = []
        for line in result.stdout.splitlines():
            name = line.strip()
            if not name or name in (".", ".."):
                continue
            is_dir = name.endswith("/")
            clean = name.rstrip("/")
            entries.append(
                DirEntry(
                    name=clean,
                    path=f"{path.rstrip('/')}/{clean}",
                    is_dir=is_dir,
                )
            )
        return entries

    async def read_file(self, path: str, *, max_bytes: int = 200_000) -> bytes:
        """按字节读取沙箱文件（二进制安全）。优先 files.read_bytes。"""
        limit = max(0, int(max_bytes))

        async def _read(sb) -> bytes:
            files = getattr(sb, "files", None)
            read_bytes = getattr(files, "read_bytes", None) if files is not None else None
            if read_bytes is not None:
                kwargs: dict = {}
                if limit > 0:
                    kwargs["range_header"] = f"bytes=0-{limit - 1}"
                try:
                    data = await read_bytes(path, **kwargs)
                except Exception:
                    # 部分实现可能不支持 Range；整文件读取后再截断
                    data = await read_bytes(path)
                if not isinstance(data, (bytes, bytearray)):
                    raise TypeError(
                        f"read_bytes returned {type(data).__name__}, expected bytes"
                    )
                return bytes(data)[:limit] if limit else bytes(data)
            return await self._read_file_via_base64(path, limit=limit)

        return await self._call_sandbox(_read)

    async def _read_file_via_base64(self, path: str, *, limit: int) -> bytes:
        """无 files API 时经 base64 文本通道读取，避免 stdout 破坏二进制。"""
        quoted = shlex.quote(path)
        result = await self.run(
            f"python3 -c \"import base64,sys; "
            f"d=open(sys.argv[1],'rb').read(int(sys.argv[2])); "
            f"sys.stdout.write(base64.b64encode(d).decode('ascii'))\" "
            f"{quoted} {limit}",
            cwd="/",
            timeout_sec=120,
        )
        if result.exit_code != 0:
            raise FileNotFoundError(result.stderr or path)
        try:
            return base64.b64decode(result.stdout.strip(), validate=False)
        except Exception as e:
            raise RuntimeError(f"sandbox read_file base64 decode failed: {path}") from e

    async def write_file(self, path: str, data: bytes) -> None:
        """写入沙箱文件；原样传递 bytes（WriteEntry 支持 str|bytes）。"""
        await self.write_files([(path, data)])

    async def write_files(self, entries: list[tuple[str, bytes]]) -> None:
        """批量写入；一次 API 调用（WriteEntry 支持 str|bytes）。"""
        if not entries:
            return

        async def _write(sb) -> None:
            write_files = getattr(getattr(sb, "files", None), "write_files", None)
            if write_files is None:
                raise RuntimeError("sandbox files.write_files unavailable")
            from opensandbox.models.filesystem import WriteEntry

            await write_files(
                [WriteEntry(path=path, data=data, mode=644) for path, data in entries]
            )

        await self._call_sandbox(_write)
