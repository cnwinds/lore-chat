from app.engine.knowledge_writer import KnowledgeWriter
from app.storage.repo import KnowledgeRepo
from app.index.indexer import Indexer
from app.models.llm import FakeLLMClient
from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex


def test_persist_document_reindexes(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    llm = FakeLLMClient(embed_dim=8)
    idx = Indexer(VectorIndex(tmp_path / "vec"), FullTextIndex(tmp_path / "fts.db"), llm)
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
