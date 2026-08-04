from __future__ import annotations

from pathlib import PurePosixPath


class KbPathError(ValueError):
    pass


def normalize_directory(directory: str) -> str:
    d = (directory or "").replace("\\", "/").strip().strip("/")
    if not d:
        return ""
    if d.startswith(".") or ".." in d.split("/"):
        raise KbPathError(f"非法目录：{directory}")
    return d


def normalize_filename(filename: str) -> str:
    f = (filename or "").replace("\\", "/").strip().strip("/")
    if not f or "/" in f:
        raise KbPathError(f"非法文件名：{filename}")
    if not f.endswith(".md"):
        raise KbPathError("filename 必须以 .md 结尾")
    if f.startswith("."):
        raise KbPathError(f"非法文件名：{filename}")
    return f


def join_kb_path(directory: str, filename: str) -> str:
    d = normalize_directory(directory)
    f = normalize_filename(filename)
    return f"{d}/{f}" if d else f


def title_from_rel_path(rel_path: str) -> str:
    return PurePosixPath(rel_path.replace("\\", "/")).stem
