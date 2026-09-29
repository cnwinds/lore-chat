"""OpenSandbox 实现的 SandboxRuntime。"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from app.engine.roles import DEFAULT_ROLE_ID
from app.engine.sandbox import probes
from app.engine.sandbox import state as sandbox_state
from app.engine.sandbox.job_drain import drain_job
from app.engine.sandbox.mirrors import (
    MirrorRegion,
    apt_configure_script,
    mirror_env,
    normalize_mirror_region,
)
from app.engine.sandbox.naming import DEFAULT_WORKSPACE_VOLUME
from app.engine.sandbox.protocol import (
    CommandResult,
    DirEntry,
    JobStatus,
    SandboxFsError,
)

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


_SANDBOX_GONE = re.compile(r"sandbox_not_found|sandbox \S+ not found")
# 与 coreutils timeout 一致
_TIMEOUT_EXIT_CODE = 124


class OpenSandboxRuntime:
    def __init__(
        self,
        *,
        kb_path: Path,
        domain: str,
        protocol: str = "http",
        api_key: str | None = None,
        use_server_proxy: bool = True,
        workspace_volume: str = DEFAULT_WORKSPACE_VOLUME,
        image: str = "lorechat-sandbox-agent:local",
        sandbox_env: dict[str, str] | None = None,
        mirror_region: MirrorRegion = "cn",
        role_id: str = DEFAULT_ROLE_ID,
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
        self.role_id = (role_id or "").strip() or DEFAULT_ROLE_ID
        self._sandbox = None
        self._sandbox_id: str | None = None
        self._applying_mirrors = False
        self._active_executions: set[str] = set()

    @property
    def _slot_default_volume(self) -> str:
        return (
            self.workspace_volume
            if self.role_id == DEFAULT_ROLE_ID
            else DEFAULT_WORKSPACE_VOLUME
        )

    def _persist_slot(
        self,
        *,
        sandbox_id: str | None = None,
        mirror_region: str | None = None,
        clear_sandbox_id: bool = False,
    ) -> None:
        sandbox_state.upsert_slot(
            self.kb_path,
            self.role_id,
            sandbox_id=sandbox_id,
            volume_name=self.workspace_volume,
            mirror_region=mirror_region,
            default_volume=self._slot_default_volume,
            clear_sandbox_id=clear_sandbox_id,
        )

    @staticmethod
    def _is_recoverable_sandbox_error(exc: BaseException) -> bool:
        """只有「沙箱会话不可达 / 沙箱已不存在」才重建；文件级错误绝不触发。"""
        if isinstance(exc, (asyncio.CancelledError, SandboxFsError)):
            return False
        name = type(exc).__name__
        if name in (
            "ConnectError",
            "ConnectTimeout",
            "ReadError",
            "WriteError",
            "SandboxConnectionException",
        ):
            return True
        mod = type(exc).__module__ or ""
        if ("httpx" in mod or "httpcore" in mod) and (
            "Connect" in name or "Timeout" in name
        ):
            return True
        err = getattr(exc, "error", None)
        text = f"{getattr(err, 'code', '') or ''} {exc}".lower()
        if _SANDBOX_GONE.search(text) or "connection attempts failed" in text:
            return True
        return False

    def _invalidate_sandbox(self, *, clear_persisted: bool) -> None:
        self._sandbox = None
        self._sandbox_id = None
        if clear_persisted:
            # 只清本角色 sandbox_id，保留 PVC 绑定
            sandbox_state.clear_slot_sandbox_id(
                self.kb_path,
                self.role_id,
                default_volume=self._slot_default_volume,
            )

    async def _call_sandbox(self, fn):
        """执行一次沙箱 API 调用；连接类失败时清缓存并重建后重试一次。

        不做热路径探活：每次 API 前多一次往返不值得，会话过期交给本方法的失败重试即可。
        """
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
        # 进程内已有句柄则直接复用；是否仍可达由 _call_sandbox 失败重建发现。
        if self._sandbox is not None and self._sandbox_id:
            if not self._applying_mirrors:
                await self._ensure_mirrors()
            return self._sandbox_id

        from opensandbox import Sandbox
        from opensandbox.models.sandboxes import PVC, Volume

        # Volume 由 OpenSandbox PVC(create_if_not_exists=True) 在控制面创建；
        # backend 无 docker CLI / docker.sock，禁止本机 docker volume create。
        config = self._connection_config()
        existing = sandbox_state.load_slot_sandbox_id(
            self.kb_path,
            self.role_id,
            default_volume=self._slot_default_volume,
        )
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
        self._persist_slot(sandbox_id=self._sandbox_id, mirror_region=self.mirror_region)
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
        applied = sandbox_state.load_slot_mirror_region(
            self.kb_path,
            self.role_id,
            default_volume=self._slot_default_volume,
        )
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
                "apply sandbox mirrors region=%s failed exit=%s output=%s",
                self.mirror_region,
                result.exit_code,
                (result.output or "")[-300:],
            )
            return
        self._persist_slot(
            sandbox_id=self._sandbox_id,
            mirror_region=self.mirror_region,
        )
        _log.info("sandbox mirrors applied region=%s", self.mirror_region)

    async def _start_on(self, sb, command: str, cwd: str) -> str:
        from opensandbox.models.execd import RunCommandOpts

        opts = RunCommandOpts(working_directory=cwd or "/workspace", background=True)
        execution = await sb.commands.run(command, opts=opts)
        eid = getattr(execution, "id", None)
        if not eid:
            raise RuntimeError("background command returned no execution id")
        eid_s = str(eid)
        self._active_executions.add(eid_s)
        return eid_s

    async def _poll_on(
        self, sb, execution_id: str, log_cursor: int | None
    ) -> JobStatus:
        status = await sb.commands.get_command_status(execution_id)
        logs_obj = await sb.commands.get_background_command_logs(
            execution_id, cursor=log_cursor
        )
        raw = getattr(logs_obj, "content", None)
        if raw is None:
            raw = getattr(logs_obj, "output", None) or ""
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

    async def run(
        self,
        command: str,
        *,
        cwd: str = "/workspace",
        timeout_sec: float | None = 120,
        _ready: bool = True,
    ) -> CommandResult:
        """跑到结束并返回逐字节输出（stdout/stderr 合流）。

        内部命令不向界面发进度；需要流式展示的走 ``SandboxExecutionEngine``。
        只有启动可重建重试：job 已启动后轮询失败直接抛出，命令不得被重跑。
        """

        async def _start(sb):
            return sb, await self._start_on(sb, command, cwd)

        if _ready:
            sb, eid = await self._call_sandbox(_start)
        else:
            if self._sandbox is None:
                raise RuntimeError("sandbox not ready")
            sb, eid = await _start(self._sandbox)

        chunks: list[str] = []
        deadline = time.monotonic() + timeout_sec if timeout_sec is not None else None
        try:
            outcome = await drain_job(
                lambda cur: self._poll_on(sb, eid, cur),
                deadline=deadline,
                on_chunk=lambda text, _cur: chunks.append(text),
            )
        except BaseException:
            await self.interrupt(eid)
            raise
        if outcome.running:
            await self.interrupt(eid)
            try:
                tail = await self._poll_on(sb, eid, outcome.cursor)
                chunks.append(tail.logs or "")
            except Exception:
                _log.debug("tail poll after timeout failed eid=%s", eid, exc_info=True)
            return CommandResult(
                output="".join(chunks),
                exit_code=_TIMEOUT_EXIT_CODE,
                execution_id=eid,
                timed_out=True,
            )
        self._active_executions.discard(eid)
        code = outcome.exit_code
        return CommandResult(
            output="".join(chunks),
            exit_code=int(code) if code is not None else 0,
            execution_id=eid,
        )

    async def start_job(self, command: str, *, cwd: str = "/workspace") -> str:
        return await self._call_sandbox(lambda sb: self._start_on(sb, command, cwd))

    async def poll_job(
        self, execution_id: str, *, log_cursor: int | None = None
    ) -> JobStatus:
        return await self._call_sandbox(
            lambda sb: self._poll_on(sb, execution_id, log_cursor)
        )

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
        result = await self.run(probes.list_dir_command(path), cwd="/", timeout_sec=30)
        return probes.decode_list_dir(path, result)

    async def read_file(self, path: str, *, max_bytes: int = 200_000) -> bytes:
        """按字节读取沙箱文件（二进制安全）。优先 files.read_bytes；失败抛分型错误。"""
        limit = max(0, int(max_bytes))

        async def _read_bytes(read_bytes, **kwargs) -> bytes:
            try:
                return await read_bytes(path, **kwargs)
            except Exception as exc:
                classified = probes.classify_sdk_fs_error(path, exc)
                if classified is not None:
                    raise classified from exc
                raise

        async def _read(sb) -> bytes:
            files = getattr(sb, "files", None)
            read_bytes = getattr(files, "read_bytes", None) if files is not None else None
            if read_bytes is None:
                return await self._read_file_via_base64(path, limit=limit)
            if limit > 0:
                try:
                    data = await _read_bytes(
                        read_bytes, range_header=f"bytes=0-{limit - 1}"
                    )
                except SandboxFsError:
                    raise
                except Exception:
                    # 部分实现可能不支持 Range；整文件读取后再截断
                    data = await _read_bytes(read_bytes)
            else:
                data = await _read_bytes(read_bytes)
            if not isinstance(data, (bytes, bytearray)):
                raise TypeError(
                    f"read_bytes returned {type(data).__name__}, expected bytes"
                )
            return bytes(data)[:limit] if limit else bytes(data)

        return await self._call_sandbox(_read)

    async def _read_file_via_base64(self, path: str, *, limit: int) -> bytes:
        """无 files API 时经探针读取（base64 包在 JSON 里，二进制安全）。"""
        result = await self.run(
            probes.read_b64_command(path, limit), cwd="/", timeout_sec=120
        )
        return probes.decode_read_b64(path, result)

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

    async def destroy_container(self, *, keep_volume: bool = True) -> None:
        """kill 执行容器；PVC 由 OpenSandbox 默认保留（pre-existing 卷不会随 kill 删除）。"""
        del keep_volume  # 控制面无独立删卷 API；是否忘记 slot 由 RoleSandboxPool 决定
        await self.interrupt_all()
        try:
            if self._sandbox is not None:
                await self._sandbox.kill()
                close = getattr(self._sandbox, "close", None)
                if close is not None:
                    await close()
            elif self._sandbox_id:
                from opensandbox import Sandbox

                sb = await Sandbox.connect(
                    self._sandbox_id, connection_config=self._connection_config()
                )
                await sb.kill()
                close = getattr(sb, "close", None)
                if close is not None:
                    await close()
        except Exception:
            _log.warning(
                "destroy sandbox container role=%s id=%s failed",
                self.role_id,
                self._sandbox_id,
                exc_info=True,
            )
        finally:
            self._invalidate_sandbox(clear_persisted=True)
