from __future__ import annotations

import re
from pathlib import PurePosixPath

from app.index.extract import extract_text
from app.index.indexer import Indexer
from app.storage import frontmatter
from app.storage.kb_paths import (
    KbPathError,
    join_kb_path,
    normalize_directory,
    title_from_rel_path,
)
from app.storage.repo import KnowledgeRepo

_ATTACHMENTS = "/attachments/"


class KbPathExistsError(FileExistsError):
    def __init__(self, rel_path: str):
        self.rel_path = rel_path
        super().__init__(f"目标路径已存在：{rel_path}")


def is_markdown_path(rel_path: str) -> bool:
    return rel_path.replace("\\", "/").lower().endswith(".md")


def is_attachment_path(rel_path: str) -> bool:
    return _ATTACHMENTS in rel_path.replace("\\", "/")


def suggest_alternate_filename(filename: str) -> str:
    base = _safe_basename(filename)
    stem = PurePosixPath(base).stem
    suffix = PurePosixPath(base).suffix
    m = re.match(r"^(.+) \((\d+)\)$", stem)
    if m:
        b, n = m.group(1), int(m.group(2))
        return f"{b} ({n + 1}){suffix}"
    return f"{stem} (1){suffix}"


def _safe_basename(name: str) -> str:
    base = PurePosixPath(name.replace("\\", "/")).name.strip()
    if not base or base in (".", ".."):
        raise ValueError("无效文件名")
    if "/" in base or ".." in base:
        raise ValueError("无效文件名")
    return base


def _attachment_rel(directory: str, filename: str) -> str:
    d = normalize_directory(directory)
    fn = _safe_basename(filename)
    return f"{d}/attachments/{fn}" if d else f"attachments/{fn}"


class KnowledgeWriter:
    """知识库 Markdown 落盘、索引与 changelog 的唯一 seam。"""

    def __init__(self, repo: KnowledgeRepo, indexer: Indexer | None = None):
        self.repo = repo
        self.indexer = indexer

    def persist_document(
        self,
        rel_path: str,
        meta: dict,
        body: str,
        *,
        commit_msg: str,
        changelog_line: str,
    ) -> str:
        norm = rel_path.replace("\\", "/").lstrip("/")
        self.repo.write_doc(norm, meta, body, commit_msg=commit_msg)
        if self.indexer is not None:
            self.indexer.reindex_doc(norm, body)
        self.repo.log_change(
            changelog_line,
            commit_msg=f"chore: changelog for {norm}",
        )
        return norm

    def save_edit(
        self,
        rel_path: str,
        meta: dict,
        old_body: str,
        new_body: str,
        *,
        affected_start: int,
        affected_end: int,
        commit_msg: str | None = None,
        changelog_line: str | None = None,
    ) -> str:
        norm = rel_path.replace("\\", "/").lstrip("/")
        msg = commit_msg or f"edit: {norm}"
        self.repo.write_doc(norm, meta, new_body, commit_msg=msg)
        reindex_mode = "full"
        if self.indexer is not None:
            reindex_mode = self.indexer.reindex_doc_after_edit(
                norm, old_body, new_body, affected_start, affected_end
            )
        self.repo.log_change(
            changelog_line or f"Agent 局部编辑 {norm}",
            commit_msg=f"chore: changelog edit {norm}",
        )
        return reindex_mode

    def index_extracted_text(self, rel_path: str, text: str) -> bool:
        """附件等非 Markdown 主文档的可检索文本入索引。"""
        if not text.strip() or self.indexer is None:
            return False
        self.indexer.reindex_doc(rel_path.replace("\\", "/").lstrip("/"), text)
        return True

    def reindex_markdown_body(self, rel_path: str, body: str) -> None:
        """维护性重建索引：文档已在 git，仅刷新 FTS/向量（不写 changelog）。"""
        if self.indexer is None:
            return
        norm = rel_path.replace("\\", "/").lstrip("/")
        self.indexer.reindex_doc(norm, body)

    def move_document(self, from_path: str, to_directory: str, to_filename: str) -> str:
        from_norm = from_path.replace("\\", "/").lstrip("/")
        to_path = join_kb_path(to_directory, to_filename)
        new_path = self.repo.move_doc(
            from_norm,
            to_path,
            commit_msg=f"move: {from_norm} -> {to_path}",
        )
        if self.indexer is not None:
            try:
                self.indexer.remove_doc(from_norm)
            except Exception:
                pass
            doc = self.repo.read_doc(new_path)
            self.indexer.reindex_doc(new_path, doc.body)
        self.repo.log_change(
            f"移动文档 {from_norm} → {new_path}",
            commit_msg=f"chore: changelog move {new_path}",
        )
        return new_path

    def drop_from_index(self, rel_paths: list[str]) -> None:
        if self.indexer is None:
            return
        for rel in rel_paths:
            if rel.endswith(".md"):
                try:
                    self.indexer.remove_doc(rel)
                except Exception:
                    pass

    def record_deletion(self, deleted_path: str, deleted_files: list[str]) -> None:
        if not deleted_files:
            return
        self.repo.log_change(
            f"删除 {deleted_path}（共 {len(deleted_files)} 个文件）",
            commit_msg=f"chore: changelog for delete {deleted_path}",
        )

    @staticmethod
    def resolve_location(args: dict) -> tuple[str | None, dict | None]:
        if "directory" not in args or "filename" not in args:
            return None, {
                "summary": "缺少 directory 或 filename",
                "sources": [],
                "error": "MISSING_PATH",
                "status": "failed",
            }
        try:
            rel = join_kb_path(str(args.get("directory", "")), str(args["filename"]))
        except KbPathError as e:
            return None, {
                "summary": str(e),
                "sources": [],
                "error": "INVALID_PATH",
                "status": "failed",
            }
        return rel, None

    def import_entry(
        self,
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
            if self.repo.abs_path(rel).exists():
                raise KbPathExistsError(rel)
            text = data.decode("utf-8", errors="replace")
            meta, body = frontmatter.parse(text)
            if not meta.get("title"):
                meta["title"] = title_from_rel_path(rel)
            meta.setdefault("source", "import")
            self.persist_document(
                rel,
                meta,
                body if body.endswith("\n") else body + "\n",
                commit_msg=f"import: {rel}",
                changelog_line=f"导入 {rel}",
            )
            return {"rel_path": rel, "kind": "markdown", "indexed": True}

        rel = _attachment_rel(directory, fn)
        if self.repo.abs_path(rel).exists():
            raise KbPathExistsError(rel)
        self.repo.save_attachment(
            normalize_directory(directory),
            fn,
            data,
            commit_msg=f"import attachment {fn}",
        )
        extracted = extract_text(self.repo.abs_path(rel))
        indexed = self.index_extracted_text(rel, extracted)
        self.repo.log_change(
            f"导入附件 {rel}",
            commit_msg=f"chore: changelog import {fn}",
        )
        return {"rel_path": rel, "kind": "attachment", "indexed": indexed}

    def move_entry(
        self,
        *,
        from_path: str,
        to_directory: str,
        to_filename: str | None = None,
    ) -> str:
        from_norm = from_path.replace("\\", "/").lstrip("/")
        if self.repo.is_protected(from_norm):
            raise ValueError(f"禁止移动：{from_path}")

        if is_markdown_path(from_norm):
            fn = to_filename or PurePosixPath(from_norm).name
            try:
                rel = join_kb_path(to_directory, fn)
            except KbPathError as e:
                raise ValueError(str(e)) from e
            if self.repo.abs_path(rel).exists():
                raise KbPathExistsError(rel)
            try:
                return self.move_document(from_norm, to_directory, fn)
            except ValueError as e:
                if "已存在" in str(e):
                    raise KbPathExistsError(rel) from e
                raise

        if not is_attachment_path(from_norm):
            raise ValueError("仅支持移动 Markdown 文档或 attachments 下的文件")

        fn = _safe_basename(to_filename or PurePosixPath(from_norm).name)
        to_rel = _attachment_rel(to_directory, fn)
        if self.repo.abs_path(to_rel).exists():
            raise KbPathExistsError(to_rel)
        new_path = self.repo.move_file(
            from_norm, to_rel, commit_msg=f"move: {from_norm} -> {to_rel}"
        )
        self.drop_from_index([from_norm])
        extracted = extract_text(self.repo.abs_path(new_path))
        self.index_extracted_text(new_path, extracted)
        self.repo.log_change(
            f"移动附件 {from_norm} → {new_path}",
            commit_msg=f"chore: changelog move {new_path}",
        )
        return new_path

    def delete_entry(self, path: str) -> list[str]:
        norm = path.replace("\\", "/").rstrip("/")
        if self.repo.is_protected(norm):
            raise ValueError(f"禁止删除：{path}")
        deleted = self.repo.delete_path(norm, commit_msg=f"delete: {norm}")
        if deleted:
            self.drop_from_index(deleted)
            self.record_deletion(norm, deleted)
        return deleted
