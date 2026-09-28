"""KB ↔ 沙箱工作区交换：stage（KB→sandbox）与 publish（sandbox→KB）。

路径策略、批量 args 规范化与 partial failure 汇总集中在此；
SandboxTools 只做 Runtime 调度与 tool dict 包装。
"""

from __future__ import annotations

import posixpath
import shlex
from pathlib import PurePosixPath

from app.engine.knowledge_writer import KbPathExistsError, KnowledgeWriter
from app.engine.sandbox.protocol import SandboxRuntime
from app.storage.kb_media_paths import is_image_filename
from app.storage.kb_paths import KbPathError

STAGE_MAX_FILES = 500
STAGE_MAX_BYTES = 50 * 1024 * 1024
_CLEAN_RESERVED = frozenset({"/workspace/conversations", "/workspace/schedules"})


def workspace_dest(raw_dest: str, *, default_from_kb: str | None = None) -> str | dict:
    """解析并校验 /workspace 下的目标路径；失败返回 error dict。"""
    if raw_dest:
        dest = posixpath.normpath(str(PurePosixPath(raw_dest)))
    elif default_from_kb:
        dest = posixpath.normpath(str(PurePosixPath("/workspace") / default_from_kb))
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


def workspace_src(sandbox_path: str) -> str | dict:
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


def _norm_kb_path(raw: object) -> str:
    kb = str(raw or "").replace("\\", "/").strip("/")
    return posixpath.normpath(kb) if kb else ""


def stage_items_from_args(args: dict) -> list[dict] | dict:
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
            kb = _norm_kb_path(raw.get("kb_path"))
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
                    "clean": raw.get("clean") is True,
                }
            )
        return items

    kb_path = _norm_kb_path(args.get("kb_path"))
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
            "clean": args.get("clean") is True,
        }
    ]


def clean_dest_error(dest: str) -> dict | None:
    """clean 会先删掉目标目录：会话 / 定时任务工作区根及其各自目录不允许整删。"""
    if dest in _CLEAN_RESERVED or posixpath.dirname(dest) in _CLEAN_RESERVED:
        return {
            "summary": f"clean 不能作用于 {dest}（会话或定时任务工作区）",
            "sources": [],
            "error": "invalid clean target",
        }
    return None


def publish_items_from_args(args: dict) -> list[dict] | dict:
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
                    "summary": f"files[{i}] 需要 sandbox_path、directory、filename",
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


def _stage_error(kb_path: str, reason: str, error: str) -> dict:
    return {
        "summary": f"{kb_path}: {reason}",
        "sources": [],
        "error": error,
        "kb_path": kb_path,
    }


class KbSandboxExchange:
    """经 KnowledgeWriter 读写的 KB↔Sandbox 交换 deep module。"""

    def __init__(self, knowledge_writer: KnowledgeWriter) -> None:
        self.knowledge_writer = knowledge_writer

    async def stage(self, runtime: SandboxRuntime, args: dict) -> dict:
        parsed = stage_items_from_args(args)
        if isinstance(parsed, dict):
            return parsed

        prepared: list[dict] = []
        items_out: list[dict] = []
        clean_dirs: list[str] = []
        total_bytes = 0
        for spec in parsed:
            kb_path = spec["kb_path"]
            dest_or_err = workspace_dest(
                spec["sandbox_path"] or "",
                default_from_kb=kb_path,
            )
            if isinstance(dest_or_err, dict):
                return {
                    **dest_or_err,
                    "summary": f"{kb_path}: {dest_or_err['summary']}",
                }
            dest = dest_or_err
            try:
                files = self.knowledge_writer.list_entry_files(kb_path)
            except (PermissionError, ValueError) as e:
                return _stage_error(kb_path, str(e), "forbidden")
            if files is None:
                if spec["clean"]:
                    return _stage_error(kb_path, "clean 只能用于目录", "invalid clean target")
                pairs = [(kb_path, dest)]
                items_out.append({"kb_path": kb_path, "sandbox_path": dest, "ok": True})
            else:
                if not files:
                    return _stage_error(kb_path, "目录下没有可投放的文件", "empty directory")
                if spec["clean"]:
                    err = clean_dest_error(dest)
                    if err is not None:
                        return err
                    clean_dirs.append(dest)
                pairs = [(f, f"{dest}/{posixpath.relpath(f, kb_path)}") for f in files]
                items_out.append(
                    {
                        "kb_path": kb_path,
                        "sandbox_path": dest,
                        "ok": True,
                        "kind": "dir",
                        "files": len(files),
                        "cleaned": spec["clean"],
                    }
                )
            if len(prepared) + len(pairs) > STAGE_MAX_FILES:
                return _stage_error(
                    kb_path,
                    f"一次最多投放 {STAGE_MAX_FILES} 个文件，请缩小目录范围",
                    "too many files",
                )
            for file_kb, file_dest in pairs:
                try:
                    data = self.knowledge_writer.read_entry_bytes(file_kb)
                except FileNotFoundError:
                    return {
                        "summary": f"知识库文件不存在：{file_kb}",
                        "sources": [],
                        "error": "not found",
                        "kb_path": file_kb,
                    }
                except (PermissionError, ValueError) as e:
                    return _stage_error(file_kb, str(e), "forbidden")
                total_bytes += len(data)
                if total_bytes > STAGE_MAX_BYTES:
                    return _stage_error(
                        kb_path,
                        f"一次最多投放 {STAGE_MAX_BYTES // (1024 * 1024)}MB，请缩小目录范围",
                        "too large",
                    )
                prepared.append(
                    {
                        "kb_path": file_kb,
                        "sandbox_path": file_dest,
                        "data": data,
                        "from_dir": files is not None,
                    }
                )

        await runtime.ensure_ready()
        if clean_dirs:
            quoted = " ".join(shlex.quote(d) for d in clean_dirs)
            res = await runtime.run(f"rm -rf -- {quoted}", cwd="/", timeout_sec=60)
            if res.exit_code != 0:
                detail = (res.stderr or res.stdout or "").strip()[:500]
                return {
                    "summary": f"清空目标目录失败，未投放任何文件：{detail}",
                    "sources": [],
                    "error": "clean failed",
                }
        parents = sorted(
            {
                str(PurePosixPath(p["sandbox_path"]).parent)
                for p in prepared
                if PurePosixPath(p["sandbox_path"]).parent not in (PurePosixPath("/"),)
            }
        )
        if parents:
            quoted = " ".join(shlex.quote(p) for p in parents)
            await runtime.run(f"mkdir -p {quoted}", cwd="/", timeout_sec=30)

        await runtime.write_files([(p["sandbox_path"], p["data"]) for p in prepared])

        # 目录内逐个文件不进 sources，避免几十个来源卡片
        sources = [
            {"type": "kb", "path": p["kb_path"]} for p in prepared if not p["from_dir"]
        ]
        lines = [f"已投放 {len(prepared)} 个文件"]
        for it in items_out:
            if it.get("kind") == "dir":
                note = f"目录，{it['files']} 个文件" + ("，已先清空目标" if it["cleaned"] else "")
                lines.append(f"- {it['kb_path']}/ → {it['sandbox_path']}/（{note}）")
            else:
                lines.append(f"- {it['kb_path']} → {it['sandbox_path']}")
        out: dict = {
            "summary": "\n".join(lines),
            "sources": sources,
            "ok": len(prepared),
            "failed": 0,
            "items": items_out,
        }
        if len(items_out) == 1:
            out["kb_path"] = items_out[0]["kb_path"]
            out["sandbox_path"] = items_out[0]["sandbox_path"]
        return out

    async def publish(
        self,
        runtime: SandboxRuntime,
        args: dict,
        *,
        allow_binary: bool = True,
    ) -> dict:
        parsed = publish_items_from_args(args)
        if isinstance(parsed, dict):
            return parsed

        await runtime.ensure_ready()
        items_out: list[dict] = []
        sources: list[dict] = []
        attachments: list[str] = []
        ok_n = 0
        for spec in parsed:
            item: dict = {
                "sandbox_path": spec["sandbox_path"],
                "directory": spec["directory"],
                "filename": spec["filename"],
            }
            norm = workspace_src(spec["sandbox_path"])
            if isinstance(norm, dict):
                item["ok"] = False
                item["error"] = norm.get("error") or "invalid path"
                item["summary"] = norm["summary"]
                items_out.append(item)
                continue
            item["sandbox_path"] = norm
            try:
                data = await runtime.read_file(norm, max_bytes=50 * 1024 * 1024)
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
                    allow_binary=allow_binary,
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
                # 图片（含 SVG）挂附件，聊天侧与 generate_image 一样出缩略图
                if is_image_filename(PurePosixPath(rel).name):
                    attachments.append(rel)

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
        if attachments:
            out["attachments"] = attachments
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


__all__ = [
    "KbSandboxExchange",
    "workspace_dest",
    "workspace_src",
    "stage_items_from_args",
    "publish_items_from_args",
]
