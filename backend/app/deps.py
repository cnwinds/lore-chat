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
from app.engine.memory.llm_extractor import LLMMemoryExtractor
from app.engine.memory.observer import MemoryObserver
from app.engine.memory_worker import MemoryWorker
from app.engine.memory_maintenance import MemoryMaintenanceJob
from app.engine.memory.decay import DecayConfig
from app.engine.organizer import Organizer
from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.chat.session_runner import ChatSessionRunner
from app.engine.agent.orchestrator import AgentOrchestrator
from app.engine.agent.system_layer import SystemLayer
from app.engine.agent.tools import ToolRegistry
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
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
    memory_worker: MemoryWorker
    memory_maintenance: MemoryMaintenanceJob
    knowledge_writer: KnowledgeWriter
    organizer: Organizer
    agent: AgentOrchestrator
    chat_runner: ChatSessionRunner
    system_layer: SystemLayer
    memory_service: MemoryService


def build_container(settings: Settings, llm: LLMClient | None = None) -> Container:
    workspace_id = ensure_workspace_id(settings.kb_path)
    llm = llm or OpenAILLMClient(settings)
    repo = KnowledgeRepo(settings.kb_path, protected_dirs=(settings.system_layer_dir,))
    memory_store = MemoryStore(
        settings.kb_path / ".kb" / "memory" / "memory.db",
        owner_key=workspace_id,
    )
    memory_service = MemoryService(
        memory_store,
        repo,
        conversations=None,
        indexer=None,
    )
    system_layer = SystemLayer(
        repo,
        dir_name=settings.system_layer_dir,
        precepts_filename=settings.precepts_filename,
        soul_filename=settings.soul_filename,
        memory_service=memory_service,
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
        repo=repo,
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
    memory_observer = MemoryObserver(
        memory_store,
        extractor=LLMMemoryExtractor(llm),
    )
    memory_worker = MemoryWorker(
        conversations, memory_service, observer=memory_observer
    )
    decay_config = DecayConfig(
        stale_days_goal_project=settings.memory_decay_stale_days,
        decay_days_inferred=settings.memory_decay_inferred_days,
        decay_days_candidate=settings.memory_decay_candidate_days,
    )
    memory_maintenance = MemoryMaintenanceJob(
        memory_store, conversations, config=decay_config
    )
    knowledge_writer = KnowledgeWriter(repo, indexer)
    organizer = Organizer(
        repo=repo,
        retriever=retriever,
        indexer=indexer,
        pending=pending,
        llm=llm,
        knowledge_writer=knowledge_writer,
    )
    memory_service.conversations = conversations
    memory_service.knowledge_writer = knowledge_writer
    from app.engine.memory.renderer import MemoryRenderer

    MemoryRenderer(repo).ensure_seed()
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
        conversation_context_max_chars=settings.conversation_context_max_chars,
        memory_service=memory_service,
        knowledge_writer=knowledge_writer,
    )
    agent = AgentOrchestrator(settings, llm, tool_registry, system_layer=system_layer)
    chat_runner = ChatSessionRunner(agent, conversations)
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
        memory_worker=memory_worker,
        memory_maintenance=memory_maintenance,
        knowledge_writer=knowledge_writer,
        organizer=organizer,
        agent=agent,
        chat_runner=chat_runner,
        system_layer=system_layer,
        memory_service=memory_service,
    )


def dispose_container(container: Container | None) -> None:
    """Close sqlite/git handles so kb_path files can be replaced during import."""
    if container is None:
        return

    def _close_sqlite(obj) -> None:
        conn = getattr(obj, "conn", None)
        if conn is None:
            return
        try:
            conn.close()
        except Exception:
            pass
        obj.conn = None

    _close_sqlite(container.conversations)
    _close_sqlite(container.conversation_fts)
    _close_sqlite(container.indexer.fulltext)
    try:
        container.repo.repo.close()
    except Exception:
        pass


def remount_container(app, llm: LLMClient | None = None) -> None:
    """Rebuild container and reattach auth/session/settings after KB import."""
    from app.auth import AuthStore, SessionStore
    from app.settings_store import SettingsStore

    old_store = app.state.settings_store
    kb_path = old_store.get().kb_path
    app.state.settings_store = SettingsStore(kb_path, old_store._base)
    settings = app.state.settings_store.get()
    app.state.container = build_container(settings, llm=llm)
    app.state.auth_store = AuthStore(kb_path)
    app.state.session_store = SessionStore(kb_path)


def apply_settings(
    container: Container, settings: Settings, llm: LLMClient | None = None
) -> None:
    container.settings = settings
    new_llm = llm or OpenAILLMClient(settings)
    container.llm = new_llm
    container.indexer.llm = new_llm
    container.retriever.llm = new_llm
    container.organizer.llm = new_llm
    container.derivation_worker.llm = new_llm
    container.agent.settings = settings
    container.agent.llm = new_llm
    container.agent.tools.web_search = WebSearch(settings)
    container.agent.tools.fetcher = WebFetcher(
        settings.fetch_url_timeout, settings.fetch_url_max_bytes
    )
    container.chat_runner = ChatSessionRunner(container.agent, container.conversations)
