from __future__ import annotations

from app.index.indexer import Indexer
from app.storage.kb_paths import KbPathError, join_kb_path
from app.storage.repo import KnowledgeRepo


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
