"""向后兼容：新代码请使用 KnowledgeWriter 与 KbTreeService。"""

from app.engine.knowledge_writer import (
    KbPathExistsError,
    KnowledgeWriter,
    is_attachment_path,
    is_markdown_path,
    suggest_alternate_filename,
)

__all__ = [
    "KbPathExistsError",
    "KnowledgeWriter",
    "is_attachment_path",
    "is_markdown_path",
    "suggest_alternate_filename",
    "import_file",
    "move_entry",
    "delete_entry",
]


def import_file(
    repo,
    writer: KnowledgeWriter,
    *,
    directory: str,
    filename: str,
    data: bytes,
) -> dict:
    return writer.import_entry(directory=directory, filename=filename, data=data)


def move_entry(
    repo,
    writer: KnowledgeWriter,
    *,
    from_path: str,
    to_directory: str,
    to_filename: str | None = None,
) -> str:
    return writer.move_entry(
        from_path=from_path,
        to_directory=to_directory,
        to_filename=to_filename,
    )


def delete_entry(repo, writer: KnowledgeWriter, path: str) -> list[str]:
    return writer.delete_entry(path)
