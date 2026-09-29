from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.index.conversation_index import ConversationIndex
from app.index.indexer import Indexer
from app.index.partitioned import LLMEmbedder, SearchIndex
from app.index.revision import IndexRevision
from app.engine.retriever import Retriever
from app.models.llm import LLMClient
from app.storage.repo import KnowledgeRepo


@dataclass
class IndexSubgraph:
    indexer: Indexer
    conversation_index: ConversationIndex
    index_revision: IndexRevision
    retriever: Retriever
    search_index: SearchIndex

    def rebind_llm(self, llm: LLMClient) -> None:
        self.retriever.llm = llm
        self.search_index.embedder = LLMEmbedder(llm)
        self.search_index.on_embedder_changed()

    def apply_settings(self, settings: Settings) -> None:
        """热应用检索 tunables（与构造时 Settings 同源）。"""
        self.retriever.min_score = settings.min_vector_score
        self.retriever.rrf_k = settings.rrf_k
        self.retriever.lane_candidate_k = settings.lane_candidate_k
        self.retriever.kb_first_throttle = settings.search_kb_first_throttle
        self.search_index.rrf_k = settings.rrf_k
        if hasattr(self.indexer, "reindex_full_threshold"):
            self.indexer.reindex_full_threshold = settings.reindex_full_threshold


def build_index_subgraph(
    settings: Settings,
    repo: KnowledgeRepo,
    llm: LLMClient,
    *,
    system_layer_prefix: str,
) -> IndexSubgraph:
    index_dir = settings.kb_path / ".kb" / "index"
    search_index = SearchIndex(
        index_dir / "partitioned.db",
        index_dir / "vec",
        LLMEmbedder(llm),
        rrf_k=settings.rrf_k,
    )
    conversation_index = ConversationIndex(search_index)
    indexer = Indexer(
        search_index,
        system_prefixes=(system_layer_prefix,),
        reindex_full_threshold=settings.reindex_full_threshold,
    )
    index_revision = IndexRevision(index_dir / "revision.txt")
    retriever = Retriever(
        search_index,
        llm,
        excluded_prefixes=(system_layer_prefix,),
        min_score=settings.min_vector_score,
        index_revision=index_revision,
        rrf_k=settings.rrf_k,
        lane_candidate_k=settings.lane_candidate_k,
        kb_first_throttle=settings.search_kb_first_throttle,
        repo=repo,
    )
    return IndexSubgraph(
        indexer=indexer,
        conversation_index=conversation_index,
        index_revision=index_revision,
        retriever=retriever,
        search_index=search_index,
    )
