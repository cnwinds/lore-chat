from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.models.llm import LLMClient, OpenAILLMClient
from app.storage.repo import KnowledgeRepo
from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.index.conversation_fts import ConversationFTS
from app.index.conversation_vector import ConversationVector
from app.index.revision import IndexRevision
from app.index.indexer import Indexer
from app.engine.retriever import Retriever
from app.engine.pending import PendingStore
from app.engine.merge_sessions import MergeSessionStore
from app.engine.conversations import ConversationStore
from app.engine.derivation_worker import DerivationWorker
from app.engine.organizer import Organizer
from app.engine.agent.orchestrator import AgentOrchestrator
from app.engine.agent.system_layer import SystemLayer
from app.engine.agent.tools import ToolRegistry
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import WebSearch
from app.engine.workspace import ensure_workspace_id


@dataclass
class Container:
    settings: Settings
    workspace_id: str
    llm: LLMClient
    repo: KnowledgeRepo
    indexer: Indexer
    retriever: Retriever
    pending: PendingStore
    merge_sessions: MergeSessionStore
    conversations: ConversationStore
    conversation_fts: ConversationFTS
    conversation_vector: ConversationVector
    index_revision: IndexRevision
    derivation_worker: DerivationWorker
    organizer: Organizer
    agent: AgentOrchestrator
    system_layer: SystemLayer


def build_container(settings: Settings, llm: LLMClient | None = None) -> Container:
    workspace_id = ensure_workspace_id(settings.kb_path)
    llm = llm or OpenAILLMClient(settings)
    repo = KnowledgeRepo(settings.kb_path, protected_dirs=(settings.system_layer_dir,))
    system_layer = SystemLayer(
        repo,
        dir_name=settings.system_layer_dir,
        precepts_filename=settings.precepts_filename,
        soul_filename=settings.soul_filename,
    )
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
        excluded_prefixes=(system_layer.prefix,),
        min_score=settings.min_vector_score,
        conversation_fts=conversation_fts,
        conversation_vector=conversation_vector,
        index_revision=index_revision,
        rrf_k=settings.rrf_k,
        lane_candidate_k=settings.lane_candidate_k,
    )
    pending = PendingStore(settings.kb_path / ".kb" / "pending.json")
    merge_sessions = MergeSessionStore(
        settings.kb_path / ".kb" / "merge_sessions.json"
    )
    conversations = ConversationStore(
        settings.kb_path / ".kb" / "conversations"
    )
    derivation_worker = DerivationWorker(
        conversations,
        conversation_fts,
        conversation_vector=conversation_vector,
        llm=llm,
        index_revision=index_revision,
        chunk_chars=settings.conversation_chunk_chars,
        overlap=settings.conversation_chunk_overlap_chars,
    )
    organizer = Organizer(
        repo=repo,
        retriever=retriever,
        indexer=indexer,
        pending=pending,
        llm=llm,
    )
    fetcher = WebFetcher(settings.fetch_url_timeout, settings.fetch_url_max_bytes)
    web_search = WebSearch(settings)
    tool_registry = ToolRegistry(
        retriever,
        repo,
        organizer,
        fetcher,
        web_search,
        pending,
        conversations=conversations,
        system_layer=system_layer,
        indexer=indexer,
        disclosure_chars=settings.read_disclosure_chars,
        edit_doc_max_edits=settings.edit_doc_max_edits,
        edit_doc_max_patch_chars=settings.edit_doc_max_patch_chars,
        edit_doc_require_read=settings.edit_doc_require_read,
    )
    agent = AgentOrchestrator(settings, llm, tool_registry, system_layer=system_layer)
    return Container(
        settings=settings,
        workspace_id=workspace_id,
        llm=llm,
        repo=repo,
        indexer=indexer,
        retriever=retriever,
        pending=pending,
        merge_sessions=merge_sessions,
        conversations=conversations,
        conversation_fts=conversation_fts,
        conversation_vector=conversation_vector,
        index_revision=index_revision,
        derivation_worker=derivation_worker,
        organizer=organizer,
        agent=agent,
        system_layer=system_layer,
    )
