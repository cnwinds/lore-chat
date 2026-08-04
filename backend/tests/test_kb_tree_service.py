import pytest

from app.engine.kb_tree_service import KbTreeService
from app.engine.knowledge_writer import KbPathExistsError, KnowledgeWriter
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.revision import IndexRevision
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo


def _svc(tmp_path, *, protected=("系统",)):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=protected)
    llm = FakeLLMClient(embed_dim=8)
    idx = Indexer(VectorIndex(tmp_path / "vec"), FullTextIndex(tmp_path / "fts.db"), llm)
    writer = KnowledgeWriter(repo, idx)
    rev = IndexRevision(tmp_path / "revision.txt")
    return KbTreeService(repo, writer, rev), repo, rev


def test_import_upload_bumps_revision(tmp_path):
    svc, repo, rev = _svc(tmp_path)
    assert rev.get() == 0
    svc.import_upload(directory="技术", filename="a.md", data=b"# Hi\n\n")
    assert rev.get() == 1
    assert repo.read_doc("技术/a.md").body.startswith("# Hi")


def test_import_protected_directory(tmp_path):
    svc, _, _ = _svc(tmp_path)
    with pytest.raises(PermissionError, match="禁止写入"):
        svc.import_upload(directory="系统", filename="x.md", data=b"x\n")


def test_move_protected_target(tmp_path):
    svc, _, _ = _svc(tmp_path)
    svc.import_upload(directory="", filename="a.md", data=b"a\n")
    with pytest.raises(PermissionError, match="禁止移动"):
        svc.move(from_path="a.md", to_directory="系统")


def test_delete_no_bump_when_missing(tmp_path):
    svc, _, rev = _svc(tmp_path)
    with pytest.raises(FileNotFoundError):
        svc.delete("missing.md")
    assert rev.get() == 0


def test_delete_bumps_when_paths_removed(tmp_path):
    svc, _, rev = _svc(tmp_path)
    svc.import_upload(directory="x", filename="f.txt", data=b"hi")
    before = rev.get()
    r = svc.delete("x/attachments/f.txt")
    assert r["deleted_paths"] == ["x/attachments/f.txt"]
    assert rev.get() == before + 1


def test_import_conflict(tmp_path):
    svc, _, _ = _svc(tmp_path)
    svc.import_upload(directory="", filename="a.md", data=b"x\n")
    with pytest.raises(KbPathExistsError):
        svc.import_upload(directory="", filename="a.md", data=b"y\n")
