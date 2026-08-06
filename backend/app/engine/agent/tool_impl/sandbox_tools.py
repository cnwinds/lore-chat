"""沙箱工具：run / list / read / publish / job_status（含确认门）。"""

from __future__ import annotations

import asyncio
from pathlib import PurePosixPath

from app.engine.chat.progress_log import ensure_line_chunk
from app.engine.knowledge_writer import KbPathExistsError, KnowledgeWriter
from app.engine.pending import PendingStore
from app.engine.sandbox.policy import command_needs_confirmation
from app.engine.sandbox.progress import emit_progress
from app.engine.sandbox.protocol import SandboxRuntime
from app.storage.kb_paths import KbPathError

_CONFIRM_OPTIONS = [
    {"id": "approve", "label": "执行"},
    {"id": "deny", "label": "取消"},
]


class SandboxTools:
    def __init__(
        self,
        runtime: SandboxRuntime | None,
        knowledge_writer: KnowledgeWriter,
        pending: PendingStore | None = None,
        *,
        trust_mode: bool = True,
        short_timeout_sec: float = 120,
        job_poll_interval_sec: float = 0.5,
        job_max_wait_sec: float = 600,
        read_max_chars: int = 50_000,
    ) -> None:
        self.runtime = runtime
        self.knowledge_writer = knowledge_writer
        self.pending = pending
        self.trust_mode = trust_mode
        self.short_timeout_sec = short_timeout_sec
        self.job_poll_interval_sec = job_poll_interval_sec
        self.job_max_wait_sec = job_max_wait_sec
        self.read_max_chars = read_max_chars

    def _require(self) -> SandboxRuntime | dict:
        if self.runtime is None:
            return {
                "summary": "当前实例未启用沙箱执行能力（请用 docker-compose.sandbox.yml 启动）",
                "sources": [],
                "error": "sandbox disabled",
            }
        return self.runtime

    @staticmethod
    def _parse_run_args(args: dict) -> tuple[str, str, bool, float | None]:
        cwd = (args.get("cwd") or "/workspace").strip() or "/workspace"
        background = bool(args.get("background", False))
        timeout = args.get("timeout_sec")
        timeout_sec = float(timeout) if timeout is not None else None
        command = (args.get("command") or "").strip()
        return command, cwd, background, timeout_sec

    def _maybe_confirm(self, args: dict, command: str) -> dict | None:
        """需要确认时返回 ask_user 形态结果；否则 None。"""
        if self.trust_mode or bool(args.get("confirmed")):
            return None
        if not command_needs_confirmation(command):
            return None
        if self.pending is None:
            return {
                "summary": "该命令需要确认，但 PendingStore 不可用",
                "sources": [],
                "error": "pending unavailable",
            }
        _, cwd, background, timeout = self._parse_run_args(args)
        qid = self.pending.create(
            f"是否在沙箱执行此命令？\n\n```\n{command}\n```\ncwd={cwd}",
            list(_CONFIRM_OPTIONS),
            {
                "kind": "sandbox_confirm",
                "command": command,
                "cwd": cwd,
                "background": background,
                "timeout_sec": timeout,
            },
        )
        return {
            "summary": "等待用户确认是否执行沙箱命令",
            "sources": [],
            "question_id": qid,
            "question": f"是否在沙箱执行？\n{command}",
            "options": list(_CONFIRM_OPTIONS),
            "awaiting_user": True,
        }

    async def sandbox_run(self, args: dict) -> dict:
        rt = self._require()
        if isinstance(rt, dict):
            return rt
        command, cwd, background, timeout = self._parse_run_args(args)
        if not command:
            return {"summary": "缺少 command", "sources": [], "error": "missing command"}

        gate = self._maybe_confirm(args, command)
        if gate is not None:
            return gate

        timeout_sec = (
            float(timeout) if timeout is not None else self.short_timeout_sec
        )

        await rt.ensure_ready()
        shown = command if len(command) <= 240 else command[:240] + "…"
        emit_progress(f"$ {shown}\n", phase="start")

        if background or timeout_sec > self.short_timeout_sec:
            eid = await rt.start_job(command, cwd=cwd)
            emit_progress(f"job started id={eid}\n", phase="job", execution_id=eid)
            cursor: int | None = None
            waited = 0.0
            full_logs = ""
            try:
                while waited < self.job_max_wait_sec:
                    status = await rt.poll_job(eid, log_cursor=cursor)
                    chunk = status.logs or ""
                    if chunk:
                        full_logs += chunk
                        emit_progress(
                            ensure_line_chunk(chunk),
                            phase="log",
                            execution_id=eid,
                        )
                    if status.next_cursor is not None:
                        cursor = status.next_cursor
                    if not status.running:
                        code = status.exit_code if status.exit_code is not None else 0
                        emit_progress(f"\n[exit {code}]", phase="end", execution_id=eid)
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
                    await asyncio.sleep(self.job_poll_interval_sec)
                    waited += self.job_poll_interval_sec
            except asyncio.CancelledError:
                await rt.interrupt(eid)
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

        try:
            result = await rt.run(command, cwd=cwd, timeout_sec=timeout_sec)
        except asyncio.CancelledError:
            raise
        body = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        emit_progress(f"\n[exit {result.exit_code}]", phase="end")
        summary_parts = [f"exit={result.exit_code}"]
        if body:
            summary_parts.append(body[:3500])
        if err:
            summary_parts.append(f"stderr:\n{err[:1000]}")
        out = {
            "summary": "\n".join(summary_parts),
            "sources": [],
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        if result.exit_code != 0:
            out["error"] = f"exit_code={result.exit_code}"
        return out

    async def sandbox_job_status(self, args: dict) -> dict:
        rt = self._require()
        if isinstance(rt, dict):
            return rt
        eid = (args.get("execution_id") or "").strip()
        if not eid:
            return {
                "summary": "缺少 execution_id",
                "sources": [],
                "error": "missing execution_id",
            }
        await rt.ensure_ready()
        status = await rt.poll_job(eid, log_cursor=None)
        state = "running" if status.running else f"exit={status.exit_code}"
        logs = (status.logs or "").strip()
        summary = f"job {eid}: {state}"
        if logs:
            summary += f"\n{logs[:3500]}"
        return {
            "summary": summary,
            "sources": [],
            "execution_id": eid,
            "running": status.running,
            "exit_code": status.exit_code,
            "stdout": status.logs,
        }

    async def sandbox_list_dir(self, args: dict) -> dict:
        rt = self._require()
        if isinstance(rt, dict):
            return rt
        path = (args.get("path") or "/workspace").strip() or "/workspace"
        await rt.ensure_ready()
        entries = await rt.list_dir(path)
        lines = [f"{'d' if e.is_dir else 'f'} {e.path}" for e in entries]
        preview = "\n".join(lines[:200])
        return {
            "summary": f"{path} 共 {len(entries)} 项\n{preview}" if entries else f"{path} 为空",
            "sources": [],
            "entries": [
                {"name": e.name, "path": e.path, "is_dir": e.is_dir} for e in entries
            ],
        }

    async def sandbox_read_file(self, args: dict) -> dict:
        rt = self._require()
        if isinstance(rt, dict):
            return rt
        path = (args.get("path") or "").strip()
        if not path:
            return {"summary": "缺少 path", "sources": [], "error": "missing path"}
        max_chars = int(args.get("max_chars") or self.read_max_chars)
        await rt.ensure_ready()
        try:
            data = await rt.read_file(path, max_bytes=max_chars * 4)
        except FileNotFoundError:
            return {
                "summary": f"文件不存在：{path}",
                "sources": [],
                "error": "not found",
            }
        text = data.decode("utf-8", errors="replace")
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]
        return {
            "summary": f"已读 {path}" + ("（已截断）" if truncated else ""),
            "sources": [],
            "content": text,
            "truncated": truncated,
            "path": path,
        }

    async def publish_from_sandbox(self, args: dict) -> dict:
        rt = self._require()
        if isinstance(rt, dict):
            return rt
        sandbox_path = (args.get("sandbox_path") or "").strip()
        directory = args.get("directory")
        filename = (args.get("filename") or "").strip()
        if not sandbox_path or directory is None or not filename:
            return {
                "summary": "需要 sandbox_path、directory、filename",
                "sources": [],
                "error": "missing fields",
            }
        norm = str(PurePosixPath(sandbox_path))
        if not (norm == "/workspace" or norm.startswith("/workspace/")):
            return {
                "summary": "仅允许发布 /workspace 下的文件",
                "sources": [],
                "error": "path not under /workspace",
            }
        await rt.ensure_ready()
        try:
            data = await rt.read_file(norm, max_bytes=50 * 1024 * 1024)
        except FileNotFoundError:
            return {
                "summary": f"沙箱文件不存在：{norm}",
                "sources": [],
                "error": "not found",
            }
        try:
            result = self.knowledge_writer.import_entry(
                directory=directory,
                filename=filename,
                data=data,
            )
        except KbPathExistsError as e:
            return {
                "summary": f"目标已存在：{e}",
                "sources": [],
                "error": "exists",
            }
        except (ValueError, KbPathError) as e:
            return {
                "summary": f"入库失败：{e}",
                "sources": [],
                "error": str(e),
            }
        rel = result.get("rel_path")
        return {
            "summary": f"已从沙箱发布到知识库：{rel}",
            "sources": [{"type": "kb", "path": rel}] if rel else [],
            "rel_path": rel,
            "kind": result.get("kind"),
        }
