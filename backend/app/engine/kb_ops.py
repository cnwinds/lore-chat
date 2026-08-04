from __future__ import annotations

import re
from pathlib import PurePosixPath

from app.index.extract import extract_text
from app.storage import frontmatter
from app.storage.kb_paths import KbPathError, join_kb_path, normalize_directory, title_from_rel_path
from app.storage.repo import KnowledgeRepo
from app.engine.knowledge_writer import KnowledgeWriter

_ATTACHMENTS = "/attachments/"


class KbPathExistsError(FileExistsError):
    def __init__(self, rel_path: str):
        self.rel_path = rel_path
        super().__init__(f"目标路径已存在：{rel_path}")


def _safe_basename(name: str) -> str:
    base = PurePosixPath(name.replace("\\", "/")).name.strip()
    if not base or base in (".", ".."):
        raise ValueError("无效文件名")
    if "/" in base or ".." in base:
        raise ValueError("无效文件名")
    return base


def is_markdown_path(rel_path: str) -> bool:
    return rel_path.replace("\\", "/").lower().endswith(".md")


def is_attachment_path(rel_path: str) -> bool:
    return _ATTACHMENTS in rel_path.replace("\\", "/")


def attachment_rel(directory: str, filename: str) -> str:
    d = normalize_directory(directory)
    fn = _safe_basename(filename)
    return f"{d}/attachments/{fn}" if d else f"attachments/{fn}"


def path_exists(repo: KnowledgeRepo, rel_path: str) -> bool:
    return repo.abs_path(rel_path).exists()


def import_file(
    repo: KnowledgeRepo,
    writer: KnowledgeWriter,
    *,
    directory: str,
    filename: str,
    data: bytes,
) -> dict:
    fn = _safe_basename(filename)
    if is_markdown_path(fn):
        try:
            rel = join_kb_path(directory, fn)
        except KbPathError as e:
            raise ValueError(str(e)) from e
        if path_exists(repo, rel):
            raise KbPathExistsError(rel)
        text = data.decode("utf-8", errors="replace")
        meta, body = frontmatter.parse(text)
        if not meta.get("title"):
            meta["title"] = title_from_rel_path(rel)
        meta.setdefault("source", "import")
        writer.persist_document(
            rel,
            meta,
            body if body.endswith("\n") else body + "\n",
            commit_msg=f"import: {rel}",
            changelog_line=f"导入 {rel}",
        )
        return {"rel_path": rel, "kind": "markdown", "indexed": True}

    rel = attachment_rel(directory, fn)
    if path_exists(repo, rel):
        raise KbPathExistsError(rel)
    repo.save_attachment(
        normalize_directory(directory),
        fn,
        data,
        commit_msg=f"import attachment {fn}",
    )
    text = extract_text(repo.abs_path(rel))
    indexed = writer.index_extracted_text(rel, text)
    repo.log_change(
        f"导入附件 {rel}",
        commit_msg=f"chore: changelog import {fn}",
    )
    return {"rel_path": rel, "kind": "attachment", "indexed": indexed}


def move_entry(
    repo: KnowledgeRepo,
    writer: KnowledgeWriter,
    *,
    from_path: str,
    to_directory: str,
    to_filename: str | None = None,
) -> str:
    from_norm = from_path.replace("\\", "/").lstrip("/")
    if repo.is_protected(from_norm):
        raise ValueError(f"禁止移动：{from_path}")

    if is_markdown_path(from_norm):
        fn = to_filename or PurePosixPath(from_norm).name
        try:
            rel = join_kb_path(to_directory, fn)
        except KbPathError as e:
            raise ValueError(str(e)) from e
        if path_exists(repo, rel):
            raise KbPathExistsError(rel)
        try:
            return writer.move_document(from_norm, to_directory, fn)
        except ValueError as e:
            if "已存在" in str(e):
                raise KbPathExistsError(rel) from e
            raise

    if not is_attachment_path(from_norm):
        raise ValueError("仅支持移动 Markdown 文档或 attachments 下的文件")

    fn = _safe_basename(to_filename or PurePosixPath(from_norm).name)
    to_rel = attachment_rel(to_directory, fn)
    if path_exists(repo, to_rel):
        raise KbPathExistsError(to_rel)
    new_path = repo.move_file(from_norm, to_rel, commit_msg=f"move: {from_norm} -> {to_rel}")
    try:
        writer.drop_from_index([from_norm])
    except Exception:
        pass
    text = extract_text(repo.abs_path(new_path))
    writer.index_extracted_text(new_path, text)
    repo.log_change(
        f"移动附件 {from_norm} → {new_path}",
        commit_msg=f"chore: changelog move {new_path}",
    )
    return new_path


def delete_entry(repo: KnowledgeRepo, writer: KnowledgeWriter, path: str) -> list[str]:
    norm = path.replace("\\", "/").rstrip("/")
    if repo.is_protected(norm):
        raise ValueError(f"禁止删除：{path}")
    deleted = repo.delete_path(norm, commit_msg=f"delete: {norm}")
    if deleted:
        writer.drop_from_index(deleted)
    if deleted:
        writer.record_deletion(norm, deleted)
    return deleted


def suggest_alternate_filename(filename: str) -> str:
    fn = _safe_basename(filename)
    stem = PurePosixPath(fn).stem
    suffix = PurePosixPath(fn).suffix
    m = re.match(r"^(.+) \((\d+)\)$", stem)
    if m:
        base, n = m.group(1), int(m.group(2))
        return f"{base} ({n + 1}){suffix}"
    return f"{stem} (1){suffix}"
