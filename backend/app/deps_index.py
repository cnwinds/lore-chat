from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.index.conversation_fts import ConversationFTS
from app.index.conversation_vector import ConversationVector
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.revision import IndexRevision
from app.index.vector import VectorIndex
from app.engine.derivation_worker import DerivationWorker
from app.engine.retriever import Retriever
from app.models.llm import LLMClient
from app.storage.repo import KnowledgeRepo


@dataclass
class IndexSubgraph:
    vector: VectorIndex
    fulltext: FullTextIndex
    indexer: Indexer
    conversation_fts: ConversationFTS
    conversation_vector: ConversationVector
    index_revision: IndexRevision
    retriever: Retriever

    def rebind_llm(
        self, llm: LLMClient, *, derivation_worker: DerivationWorker | None = None
    ) -> None:
        self.indexer.llm = llm
        self.retriever.llm = llm
        if derivation_worker is not None:
            derivation_worker.llm = llm

    def apply_settings(self, settings: Settings) -> None:
        """热应用检索 tunables（与构造时 Settings 同源）。"""
        self.retriever.min_score = settings.min_vector_score
        self.retriever.rrf_k = settings.rrf_k
        self.retriever.lane_candidate_k = settings.lane_candidate_k
        self.retriever.kb_first_throttle = settings.search_kb_first_throttle
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
    vector = VectorIndex(index_dir / "vec")
    fulltext = FullTextIndex(index_dir / "fts.db")
    indexer = Indexer(
        vector, fulltext, llm, reindex_full_threshold=settings.reindex_full_threshold
    )
    conversation_fts = ConversationFTS(index_dir / "conversation_fts.db")
    conversation_vector = ConversationVector(index_dir / "vec")
    index_revision = IndexRevision(index_dir / "revision.txt")
    retriever = Retriever(
        vector,
        fulltext,
        llm,
        excluded_prefixes=(system_layer_prefix,),
        min_score=settings.min_vector_score,
        conversation_fts=conversation_fts,
        conversation_vector=conversation_vector,
        index_revision=index_revision,
        rrf_k=settings.rrf_k,
        lane_candidate_k=settings.lane_candidate_k,
        kb_first_throttle=settings.search_kb_first_throttle,
        repo=repo,
    )
    return IndexSubgraph(
        vector=vector,
        fulltext=fulltext,
        indexer=indexer,
        conversation_fts=conversation_fts,
        conversation_vector=conversation_vector,
        index_revision=index_revision,
        retriever=retriever,
    )
