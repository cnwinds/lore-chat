import pytest

from app.engine.kb_ops import (
    KbPathExistsError,
    import_file,
    move_entry,
    delete_entry,
    suggest_alternate_filename,
)
from app.engine.knowledge_writer import KnowledgeWriter
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo


def _writer(repo, tmp_path):
    llm = FakeLLMClient(embed_dim=8)
    idx = Indexer(VectorIndex(tmp_path / "vec"), FullTextIndex(tmp_path / "fts.db"), llm)
    return KnowledgeWriter(repo, idx)


def test_import_md_and_attachment(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    w = _writer(repo, tmp_path)
    r1 = import_file(
        repo, w, directory="技术", filename="note.md", data=b"# Hi\nbody\n"
    )
    assert r1["kind"] == "markdown"
    assert repo.read_doc("技术/note.md").body.strip().startswith("# Hi")

    r2 = import_file(
        repo, w, directory="技术", filename="plan.pdf", data=b"%PDF fake"
    )
    assert r2["rel_path"] == "技术/attachments/plan.pdf"
    assert "技术/attachments/plan.pdf" in repo.list_tree()


def test_import_conflict(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = _writer(repo, tmp_path)
    import_file(repo, w, directory="", filename="a.md", data=b"x\n")
    with pytest.raises(KbPathExistsError):
        import_file(repo, w, directory="", filename="a.md", data=b"y\n")
    assert suggest_alternate_filename("a.md") == "a (1).md"


def test_move_attachment(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = _writer(repo, tmp_path)
    import_file(repo, w, directory="a", filename="f.txt", data=b"hello")
    new = move_entry(
        repo, w, from_path="a/attachments/f.txt", to_directory="b", to_filename="f.txt"
    )
    assert new == "b/attachments/f.txt"
    assert not repo.abs_path("a/attachments/f.txt").exists()


def test_delete_attachment(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = _writer(repo, tmp_path)
    import_file(repo, w, directory="x", filename="z.bin", data=b"\x00")
    deleted = delete_entry(repo, w, "x/attachments/z.bin")
    assert deleted == ["x/attachments/z.bin"]
