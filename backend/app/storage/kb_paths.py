from __future__ import annotations

from pathlib import PurePosixPath


class KbPathError(ValueError):
    pass


def _reject_internal_segments(label: str, value: str) -> None:
    norm = value.replace("\\", "/")
    if "conv:" in norm.lower():
        raise KbPathError(f"{label} 不得包含 conv: 等内部前缀")
    for seg in norm.split("/"):
        if not seg:
            continue
        if seg.startswith(".") or seg == "..":
            raise KbPathError(f"非法{label}：{value}")
        if seg.lower().startswith("conv:"):
            raise KbPathError(f"{label} 不得使用会话内部前缀：{seg}")


def normalize_directory(directory: str) -> str:
    d = (directory or "").replace("\\", "/").strip().strip("/")
    if not d:
        return ""
    if d.startswith(".") or ".." in d.split("/"):
        raise KbPathError(f"非法目录：{directory}")
    _reject_internal_segments("目录", d)
    return d


def normalize_filename(filename: str) -> str:
    f = (filename or "").replace("\\", "/").strip().strip("/")
    if not f or "/" in f:
        raise KbPathError(f"非法文件名：{filename}")
    if not f.endswith(".md"):
        raise KbPathError("filename 必须以 .md 结尾")
    if f.startswith("."):
        raise KbPathError(f"非法文件名：{filename}")
    _reject_internal_segments("文件名", f)
    return f


def join_kb_path(directory: str, filename: str) -> str:
    d = normalize_directory(directory)
    f = normalize_filename(filename)
    return f"{d}/{f}" if d else f


def join_kb_directory(base: str, folder_name: str) -> str:
    """拼接知识库目录路径（文件夹名，非 Markdown 文件名）。"""
    parent = normalize_directory(base)
    name = (folder_name or "").replace("\\", "/").strip().strip("/")
    if not name or "/" in name:
        raise KbPathError(f"非法文件夹名：{folder_name}")
    if name.startswith("."):
        raise KbPathError(f"非法文件夹名：{folder_name}")
    _reject_internal_segments("文件夹名", name)
    return f"{parent}/{name}" if parent else name


def title_from_rel_path(rel_path: str) -> str:
    return PurePosixPath(rel_path.replace("\\", "/")).stem
