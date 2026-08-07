"""沙箱工具：run / list / read / publish / stage / job_status（含确认门）。"""

from __future__ import annotations

import asyncio
import posixpath
import shlex
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
        # 命令提示行由前端用 query 渲染，不写入 progress_log，避免重复。

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

    @staticmethod
    def _workspace_dest(raw_dest: str, *, default_from_kb: str | None = None) -> str | dict:
        """解析并校验 /workspace 下的目标路径；失败返回 error dict。"""
        if raw_dest:
            dest = posixpath.normpath(str(PurePosixPath(raw_dest)))
        elif default_from_kb:
            dest = posixpath.normpath(
                str(PurePosixPath("/workspace") / default_from_kb)
            )
        else:
            return {
                "summary": "缺少 sandbox_path",
                "sources": [],
                "error": "missing sandbox_path",
            }
        if dest != "/workspace" and not dest.startswith("/workspace/"):
            return {
                "summary": "sandbox_path 必须在 /workspace 下",
                "sources": [],
                "error": "path not under /workspace",
            }
        if dest == "/workspace":
            return {
                "summary": "sandbox_path 不能是 /workspace 目录本身",
                "sources": [],
                "error": "invalid sandbox_path",
            }
        return dest

    @staticmethod
    def _workspace_src(sandbox_path: str) -> str | dict:
        norm = str(PurePosixPath(sandbox_path))
        if not (norm == "/workspace" or norm.startswith("/workspace/")):
            return {
                "summary": "仅允许发布 /workspace 下的文件",
                "sources": [],
                "error": "path not under /workspace",
            }
        if norm == "/workspace":
            return {
                "summary": "sandbox_path 不能是 /workspace 目录本身",
                "sources": [],
                "error": "invalid sandbox_path",
            }
        return norm

    def _stage_items_from_args(self, args: dict) -> list[dict] | dict:
        """规范化投放列表；失败返回 error dict。"""
        files = args.get("files")
        if files is not None:
            if not isinstance(files, list) or not files:
                return {
                    "summary": "files 须为非空数组",
                    "sources": [],
                    "error": "invalid files",
                }
            items: list[dict] = []
            for i, raw in enumerate(files):
                if not isinstance(raw, dict):
                    return {
                        "summary": f"files[{i}] 须为对象",
                        "sources": [],
                        "error": "invalid files",
                    }
                kb = (raw.get("kb_path") or "").replace("\\", "/").lstrip("/")
                if not kb:
                    return {
                        "summary": f"files[{i}] 缺少 kb_path",
                        "sources": [],
                        "error": "missing kb_path",
                    }
                items.append(
                    {
                        "kb_path": kb,
                        "sandbox_path": (raw.get("sandbox_path") or "").strip() or None,
                    }
                )
            return items

        kb_path = (args.get("kb_path") or "").replace("\\", "/").lstrip("/")
        if not kb_path:
            return {
                "summary": "需要 files（推荐）或 kb_path",
                "sources": [],
                "error": "missing kb_path",
            }
        return [
            {
                "kb_path": kb_path,
                "sandbox_path": (args.get("sandbox_path") or "").strip() or None,
            }
        ]

    def _publish_items_from_args(self, args: dict) -> list[dict] | dict:
        """规范化发布列表；失败返回 error dict。"""
        files = args.get("files")
        if files is not None:
            if not isinstance(files, list) or not files:
                return {
                    "summary": "files 须为非空数组",
                    "sources": [],
                    "error": "invalid files",
                }
            items: list[dict] = []
            for i, raw in enumerate(files):
                if not isinstance(raw, dict):
                    return {
                        "summary": f"files[{i}] 须为对象",
                        "sources": [],
                        "error": "invalid files",
                    }
                sandbox_path = (raw.get("sandbox_path") or "").strip()
                directory = raw.get("directory")
                filename = (raw.get("filename") or "").strip()
                if not sandbox_path or directory is None or not filename:
                    return {
                        "summary": (
                            f"files[{i}] 需要 sandbox_path、directory、filename"
                        ),
                        "sources": [],
                        "error": "missing fields",
                    }
                items.append(
                    {
                        "sandbox_path": sandbox_path,
                        "directory": directory,
                        "filename": filename,
                    }
                )
            return items

        sandbox_path = (args.get("sandbox_path") or "").strip()
        directory = args.get("directory")
        filename = (args.get("filename") or "").strip()
        if not sandbox_path or directory is None or not filename:
            return {
                "summary": "需要 files（推荐）或 sandbox_path+directory+filename",
                "sources": [],
                "error": "missing fields",
            }
        return [
            {
                "sandbox_path": sandbox_path,
                "directory": directory,
                "filename": filename,
            }
        ]

    async def publish_from_sandbox(self, args: dict) -> dict:
        rt = self._require()
        if isinstance(rt, dict):
            return rt
        parsed = self._publish_items_from_args(args)
        if isinstance(parsed, dict):
            return parsed

        await rt.ensure_ready()
        items_out: list[dict] = []
        sources: list[dict] = []
        ok_n = 0
        for spec in parsed:
            item: dict = {
                "sandbox_path": spec["sandbox_path"],
                "directory": spec["directory"],
                "filename": spec["filename"],
            }
            norm = self._workspace_src(spec["sandbox_path"])
            if isinstance(norm, dict):
                item["ok"] = False
                item["error"] = norm.get("error") or "invalid path"
                item["summary"] = norm["summary"]
                items_out.append(item)
                continue
            item["sandbox_path"] = norm
            try:
                data = await rt.read_file(norm, max_bytes=50 * 1024 * 1024)
            except FileNotFoundError:
                item["ok"] = False
                item["error"] = "not found"
                item["summary"] = f"沙箱文件不存在：{norm}"
                items_out.append(item)
                continue
            try:
                result = self.knowledge_writer.import_entry(
                    directory=spec["directory"],
                    filename=spec["filename"],
                    data=data,
                )
            except KbPathExistsError as e:
                item["ok"] = False
                item["error"] = "exists"
                item["summary"] = f"目标已存在：{e}"
                items_out.append(item)
                continue
            except (ValueError, KbPathError) as e:
                item["ok"] = False
                item["error"] = str(e)
                item["summary"] = f"入库失败：{e}"
                items_out.append(item)
                continue
            rel = result.get("rel_path")
            item["ok"] = True
            item["rel_path"] = rel
            item["kind"] = result.get("kind")
            item["summary"] = f"已发布 → {rel}"
            items_out.append(item)
            ok_n += 1
            if rel:
                sources.append({"type": "kb", "path": rel})

        failed_n = len(items_out) - ok_n
        lines = [
            f"发布 {ok_n}/{len(items_out)} 成功"
            + (f"，失败 {failed_n}" if failed_n else "")
        ]
        for it in items_out:
            mark = "ok" if it.get("ok") else "fail"
            detail = it.get("rel_path") or it.get("summary") or it.get("error")
            lines.append(f"- [{mark}] {it.get('sandbox_path')} → {detail}")
        out: dict = {
            "summary": "\n".join(lines),
            "sources": sources,
            "ok": ok_n,
            "failed": failed_n,
            "items": items_out,
        }
        if failed_n:
            out["error"] = f"{failed_n} file(s) failed"
        if len(items_out) == 1:
            only = items_out[0]
            if only.get("rel_path"):
                out["rel_path"] = only["rel_path"]
            if only.get("kind"):
                out["kind"] = only["kind"]
            if only.get("error") and not only.get("ok"):
                out["error"] = only["error"]
        return out

    async def stage_to_sandbox(self, args: dict) -> dict:
        rt = self._require()
        if isinstance(rt, dict):
            return rt
        parsed = self._stage_items_from_args(args)
        if isinstance(parsed, dict):
            return parsed

        prepared: list[dict] = []
        for spec in parsed:
            kb_path = spec["kb_path"]
            dest_or_err = self._workspace_dest(
                spec["sandbox_path"] or "",
                default_from_kb=kb_path,
            )
            if isinstance(dest_or_err, dict):
                return {
                    **dest_or_err,
                    "summary": f"{kb_path}: {dest_or_err['summary']}",
                }
            dest = dest_or_err
            abs_kb = self.knowledge_writer.repo.abs_path(kb_path)
            if not abs_kb.exists() or not abs_kb.is_file():
                return {
                    "summary": f"知识库文件不存在：{kb_path}",
                    "sources": [],
                    "error": "not found",
                    "kb_path": kb_path,
                }
            try:
                data = self.knowledge_writer.repo.read_bytes(kb_path)
            except FileNotFoundError:
                return {
                    "summary": f"知识库文件不存在：{kb_path}",
                    "sources": [],
                    "error": "not found",
                    "kb_path": kb_path,
                }
            prepared.append({"kb_path": kb_path, "sandbox_path": dest, "data": data})

        await rt.ensure_ready()
        parents = sorted(
            {
                str(PurePosixPath(p["sandbox_path"]).parent)
                for p in prepared
                if PurePosixPath(p["sandbox_path"]).parent not in (PurePosixPath("/"),)
            }
        )
        if parents:
            quoted = " ".join(shlex.quote(p) for p in parents)
            await rt.run(f"mkdir -p {quoted}", cwd="/", timeout_sec=30)

        await rt.write_files([(p["sandbox_path"], p["data"]) for p in prepared])

        items_out = [
            {
                "kb_path": p["kb_path"],
                "sandbox_path": p["sandbox_path"],
                "ok": True,
            }
            for p in prepared
        ]
        sources = [{"type": "kb", "path": p["kb_path"]} for p in prepared]
        lines = [f"已投放 {len(items_out)} 个文件"]
        for it in items_out:
            lines.append(f"- {it['kb_path']} → {it['sandbox_path']}")
        out: dict = {
            "summary": "\n".join(lines),
            "sources": sources,
            "ok": len(items_out),
            "failed": 0,
            "items": items_out,
        }
        if len(items_out) == 1:
            out["kb_path"] = items_out[0]["kb_path"]
            out["sandbox_path"] = items_out[0]["sandbox_path"]
        return out
