import pytest

from app.engine.knowledge_writer import KnowledgeWriter, KnowledgeWriterReadOnly
from app.storage.repo import KnowledgeRepo


@pytest.fixture
def writer(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    return KnowledgeWriter(repo, None, read_only=True)


def test_persist_document_is_refused(writer):
    with pytest.raises(KnowledgeWriterReadOnly):
        writer.persist_document(
            "技术/a.md", {}, "正文", commit_msg="x", changelog_line="x"
        )


def test_import_entry_is_refused(writer):
    with pytest.raises(KnowledgeWriterReadOnly):
        writer.import_entry(directory="技术", filename="a.png", data=b"x")


def test_move_entry_is_refused(writer):
    with pytest.raises(KnowledgeWriterReadOnly):
        writer.move_entry(from_path="技术/a.md", to_directory="产品")


def test_delete_entry_is_refused(writer):
    with pytest.raises(KnowledgeWriterReadOnly):
        writer.delete_entry("技术/a.md")


def test_update_document_meta_is_refused(writer):
    with pytest.raises(KnowledgeWriterReadOnly):
        writer.update_document_meta("技术/a.md", {"title": "x"})


def test_reads_still_work(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    rw = KnowledgeWriter(repo, None)
    rw.persist_document(
        "技术/a.md", {"title": "A"}, "正文", commit_msg="init", changelog_line="init"
    )
    ro = KnowledgeWriter(repo, None, read_only=True)
    assert ro.read_entry_bytes("技术/a.md")
