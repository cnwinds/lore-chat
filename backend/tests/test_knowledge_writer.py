from app.engine.knowledge_writer import KnowledgeWriter
from app.storage.repo import KnowledgeRepo
from app.index.indexer import Indexer
from app.index.kb_index import KB_FAMILY, KB_PARTITION
from app.index.partitioned import PartitionTuning
from app.index.search_query import compile_search_query
from app.models.llm import FakeLLMClient
from tests.helpers import make_search_index


def _fts_has_doc(search_index, doc_id: str, query: str) -> bool:
    compiled = compile_search_query(query)
    res = search_index.search(
        query,
        partitions=[KB_PARTITION],
        limit=5,
        tunings={KB_FAMILY: PartitionTuning(fts_k=5, vec_k=5)},
        fts_mode="keywords",
        vector_text=compiled.vector_text,
        lanes=("fts",),
    )
    return any(h.meta.get("source") == doc_id for h in res.lanes.get(f"{KB_FAMILY}:fts", []))


def test_persist_document_reindexes(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    llm = FakeLLMClient(embed_dim=8)
    si = make_search_index(tmp_path, llm)
    idx = Indexer(si)
    writer = KnowledgeWriter(repo, idx)
    writer.persist_document(
        "技术/a.md",
        {"title": "A"},
        "hello\n",
        commit_msg="add",
        changelog_line="创建 技术/a.md",
    )
    doc = repo.read_doc("技术/a.md")
    assert doc.body == "hello\n"


def test_persist_document_restores_download_image_urls(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    writer = KnowledgeWriter(repo, None)
    writer.persist_document(
        "pics.md",
        {"title": "P"},
        "![a](/api/download?path=generated%2Fx.png)\n",
        commit_msg="add",
        changelog_line="创建 pics.md",
    )
    assert repo.read_doc("pics.md").body == "![a](generated/x.png)\n"


def test_import_entry_file(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    llm = FakeLLMClient(embed_dim=8)
    si = make_search_index(tmp_path, llm)
    idx = Indexer(si)
    writer = KnowledgeWriter(repo, idx)
    r = writer.import_entry(directory="d", filename="n.pdf", data=b"%PDF fake")
    assert r["kind"] == "file"
    assert r["rel_path"] == "d/n.pdf"
    assert repo.abs_path("d/n.pdf").exists()


def test_move_directory_entry(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    repo.write_doc("projects/mini-app/a.md", {"title": "A"}, "a\n", commit_msg="add")
    llm = FakeLLMClient(embed_dim=8)
    si = make_search_index(tmp_path, llm)
    idx = Indexer(si)
    writer = KnowledgeWriter(repo, idx)
    new_root = writer.move_directory_entry(
        from_path="projects/mini-app",
        to_directory="archive",
    )
    assert new_root == "archive/mini-app"
    assert repo.read_doc("archive/mini-app/a.md").body == "a\n"
    assert "projects/mini-app/a.md" not in repo.list_tree()


def test_reindex_markdown_body_without_changelog(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    repo.write_doc("b.md", {"title": "B"}, "one\n", commit_msg="add b")
    llm = FakeLLMClient(embed_dim=8)
    si = make_search_index(tmp_path, llm)
    idx = Indexer(si)
    writer = KnowledgeWriter(repo, idx)
    writer.reindex_markdown_body("b.md", "one\n")
    assert _fts_has_doc(idx.search_index, "b.md", "one")
