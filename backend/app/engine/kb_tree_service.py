from __future__ import annotations

from app.engine.kb_skill import norm_dir
from app.engine.knowledge_writer import (
    KbPathExistsError,
    KnowledgeWriter,
    suggest_alternate_filename,
)
from app.index.revision import IndexRevision
from app.storage.repo import KnowledgeRepo


class KbTreeService:
    """知识库树 import/move/delete：protected 校验、写入 seam、索引 revision。"""

    def __init__(
        self,
        repo: KnowledgeRepo,
        writer: KnowledgeWriter,
        index_revision: IndexRevision,
        *,
        skills_dir: str = "技能",
    ):
        self.repo = repo
        self.writer = writer
        self.index_revision = index_revision
        self.skills_dir = norm_dir(skills_dir) or "技能"

    def import_upload(
        self, *, directory: str, filename: str, data: bytes
    ) -> dict:
        d = directory.strip()
        if d and self.repo.is_protected(f"{d}/.md"):
            raise PermissionError("禁止写入该目录")
        result = self.writer.import_entry(
            directory=d,
            filename=filename.strip(),
            data=data,
            allow_binary=True,
        )
        self.index_revision.bump()
        return result

    def move(
        self,
        *,
        from_path: str,
        to_directory: str,
        to_filename: str | None = None,
    ) -> dict:
        if self.repo.is_protected(to_directory):
            raise PermissionError("禁止移动到该目录")
        new_path = self.writer.move_entry(
            from_path=from_path,
            to_directory=to_directory,
            to_filename=to_filename,
        )
        self.index_revision.bump()
        return {"rel_path": new_path, "from_path": from_path}

    def delete(self, path: str) -> dict:
        deleted = self.writer.delete_entry(path)
        if deleted:
            self.index_revision.bump()
        return {"deleted_paths": deleted}

    def discover_skills(self, from_dir: str) -> list[str]:
        from app.engine.kb_skill import discover_skill_roots
        from app.engine.skills_dir import clamp_skills_scan_dir

        try:
            norm = clamp_skills_scan_dir(from_dir, self.skills_dir)
        except ValueError as e:
            raise PermissionError(str(e)) from e
        if self.repo.is_protected(norm):
            raise PermissionError("禁止扫描该目录")
        return discover_skill_roots(
            self.repo, norm, skills_dir=self.skills_dir
        )


__all__ = [
    "KbTreeService",
    "KbPathExistsError",
    "suggest_alternate_filename",
]
