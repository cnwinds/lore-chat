from __future__ import annotations

from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.organizer import IngestResult, Organizer
from app.engine.write_policy import WriteMode, resolve_write_mode
from app.storage.repo import KnowledgeRepo

__all__ = ["KbEntryOps", "WriteMode", "resolve_write_mode"]


class KbEntryOps:
    """Agent 与 HTTP 共用的知识库条目变更 seam（写/移/删）。"""

    def __init__(
        self,
        *,
        repo: KnowledgeRepo,
        writer: KnowledgeWriter,
        organizer: Organizer,
    ) -> None:
        self.repo = repo
        self.writer = writer
        self.organizer = organizer

    def write_text(
        self,
        content: str,
        *,
        rel_path: str,
        write_mode: WriteMode = "auto",
        conversation_id: str | None = None,
    ) -> IngestResult:
        return self.organizer.ingest_text(
            content,
            forced_rel_path=rel_path,
            write_mode=write_mode,
            conversation_id=conversation_id,
        )

    def move_entry(
        self,
        *,
        from_path: str,
        to_directory: str,
        to_filename: str | None = None,
    ) -> str:
        return self.writer.move_entry(
            from_path=from_path,
            to_directory=to_directory,
            to_filename=to_filename,
        )

    def delete_entry(self, path: str) -> list[str]:
        return self.writer.delete_entry(path)
