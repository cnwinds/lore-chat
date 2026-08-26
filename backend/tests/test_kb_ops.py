from app.engine.knowledge_writer import (
    KbPathExistsError,
    KnowledgeWriter,
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


def test_import_md_and_file(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    w = _writer(repo, tmp_path)
    r1 = w.import_entry(directory="技术", filename="note.md", data=b"# Hi\nbody\n")
    assert r1["kind"] == "markdown"
    assert repo.read_doc("技术/note.md").body.strip().startswith("# Hi")

    r2 = w.import_entry(directory="技术", filename="plan.pdf", data=b"%PDF fake")
    assert r2["kind"] == "file"
    assert r2["rel_path"] == "技术/plan.pdf"
    assert "技术/plan.pdf" in repo.list_tree()


def test_import_script(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = _writer(repo, tmp_path)
    r = w.import_entry(
        directory="scripts",
        filename="gen_audio.sh",
        data=b"#!/bin/sh\necho ok\n",
    )
    assert r["kind"] == "file"
    assert r["rel_path"] == "scripts/gen_audio.sh"
    assert repo.abs_path("scripts/gen_audio.sh").exists()


def test_import_conflict(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = _writer(repo, tmp_path)
    w.import_entry(directory="", filename="a.md", data=b"x\n")
    with pytest.raises(KbPathExistsError):
        w.import_entry(directory="", filename="a.md", data=b"y\n")
    assert suggest_alternate_filename("a.md") == "a (1).md"


def test_import_file_same_bytes_reuses_path(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = _writer(repo, tmp_path)
    data = b"\xff\xd8\xff fakejpeg"
    r1 = w.import_entry(directory="未分类", filename="shot.jpg", data=data)
    r2 = w.import_entry(directory="未分类", filename="shot.jpg", data=data)
    assert r1["rel_path"] == "未分类/shot.jpg"
    assert r2["rel_path"] == "未分类/shot.jpg"
    assert r2.get("reused") is True
    with pytest.raises(KbPathExistsError):
        w.import_entry(directory="未分类", filename="shot.jpg", data=b"different")


def test_move_file(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = _writer(repo, tmp_path)
    w.import_entry(directory="a", filename="f.pdf", data=b"%PDF fake")
    new = w.move_entry(
        from_path="a/f.pdf", to_directory="b", to_filename="f.pdf"
    )
    assert new == "b/f.pdf"
    assert not repo.abs_path("a/f.pdf").exists()


def test_rename_file(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = _writer(repo, tmp_path)
    w.import_entry(directory="scripts", filename="run.sh", data=b"#!/bin/sh\necho hi\n")

    new = w.move_entry(
        from_path="scripts/run.sh", to_directory="scripts", to_filename="start.sh"
    )
    assert new == "scripts/start.sh"
    assert repo.abs_path("scripts/start.sh").read_text(encoding="utf-8").startswith(
        "#!/bin/sh"
    )
    assert not repo.abs_path("scripts/run.sh").exists()


def test_move_document_follows_live_share(tmp_path):
    from app.models.share_links import ShareLinkStore

    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = _writer(repo, tmp_path)
    w.persist_document(
        "备忘/旧名.md",
        {"title": "旧名"},
        "hello\n",
        commit_msg="add: 备忘/旧名.md",
        changelog_line="add 旧名",
    )
    store = ShareLinkStore(repo.root)
    store.create(
        type="doc",
        title="旧名.md",
        payload_ref="备忘/旧名.md",
        ttl_sec=None,
        options={"pin_version": False, "source_path": "备忘/旧名.md"},
        share_id="followshare12345678",
    )
    new = w.move_entry(
        from_path="备忘/旧名.md", to_directory="备忘", to_filename="新名.md"
    )
    assert new == "备忘/新名.md"
    link = store.get("followshare12345678")
    assert link is not None
    assert link.payload_ref == "备忘/新名.md"
    assert link.options["source_path"] == "备忘/新名.md"


def test_delete_file(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = _writer(repo, tmp_path)
    w.import_entry(directory="x", filename="z.bin", data=b"\x00")
    deleted = w.delete_entry("x/z.bin")
    assert deleted == ["x/z.bin"]


def test_path_helpers():
    assert is_markdown_path("a.md")
    assert not is_markdown_path("a.pdf")
