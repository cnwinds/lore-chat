from app.engine.knowledge_writer import KnowledgeWriter
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo


def make_writer(repo: KnowledgeRepo, tmp_path, *, embed_dim: int = 8) -> KnowledgeWriter:
    llm = FakeLLMClient(embed_dim=embed_dim)
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    idx = Indexer(vi, fi, llm)
    return KnowledgeWriter(repo, idx)
