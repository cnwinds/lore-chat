from app.engine.knowledge_writer import (
    KbPathExistsError,
    KnowledgeWriter,
    is_attachment_path,
    is_markdown_path,
    suggest_alternate_filename,
)
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo
import pytest


def _writer(repo, tmp_path):
    llm = FakeLLMClient(embed_dim=8)
    idx = Indexer(VectorIndex(tmp_path / "vec"), FullTextIndex(tmp_path / "fts.db"), llm)
    return KnowledgeWriter(repo, idx)


def test_import_md_and_attachment(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    w = _writer(repo, tmp_path)
    r1 = w.import_entry(directory="技术", filename="note.md", data=b"# Hi\nbody\n")
    assert r1["kind"] == "markdown"
    assert repo.read_doc("技术/note.md").body.strip().startswith("# Hi")

    r2 = w.import_entry(directory="技术", filename="plan.pdf", data=b"%PDF fake")
    assert r2["rel_path"] == "技术/attachments/plan.pdf"
    assert "技术/attachments/plan.pdf" in repo.list_tree()


def test_import_conflict(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = _writer(repo, tmp_path)
    w.import_entry(directory="", filename="a.md", data=b"x\n")
    with pytest.raises(KbPathExistsError):
        w.import_entry(directory="", filename="a.md", data=b"y\n")
    assert suggest_alternate_filename("a.md") == "a (1).md"


def test_move_attachment(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = _writer(repo, tmp_path)
    w.import_entry(directory="a", filename="f.txt", data=b"hello")
    new = w.move_entry(
        from_path="a/attachments/f.txt", to_directory="b", to_filename="f.txt"
    )
    assert new == "b/attachments/f.txt"
    assert not repo.abs_path("a/attachments/f.txt").exists()


def test_delete_attachment(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = _writer(repo, tmp_path)
    w.import_entry(directory="x", filename="z.bin", data=b"\x00")
    deleted = w.delete_entry("x/attachments/z.bin")
    assert deleted == ["x/attachments/z.bin"]


def test_path_helpers():
    assert is_markdown_path("a.md")
    assert is_attachment_path("d/attachments/x.bin")
