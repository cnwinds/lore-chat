from app.config import Settings
from app.deps_index import build_index_subgraph
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo


def test_index_subgraph_apply_settings_updates_retriever(tmp_path):
    repo = KnowledgeRepo(tmp_path / "kb")
    settings = Settings(
        kb_path=tmp_path / "kb",
        min_vector_score=0.2,
        rrf_k=40,
        lane_candidate_k=15,
    )
    llm = FakeLLMClient(embed_dim=8)
    sub = build_index_subgraph(settings, repo, llm, system_layer_prefix="系统/")
    assert sub.retriever.min_score == 0.2
    assert sub.retriever.rrf_k == 40
    assert sub.retriever.lane_candidate_k == 15

    next_settings = Settings(
        kb_path=tmp_path / "kb",
        min_vector_score=0.55,
        rrf_k=80,
        lane_candidate_k=30,
        reindex_full_threshold=1000,
    )
    sub.apply_settings(next_settings)
    assert sub.retriever.min_score == 0.55
    assert sub.retriever.rrf_k == 80
    assert sub.retriever.lane_candidate_k == 30
    assert sub.indexer.reindex_full_threshold == 1000
