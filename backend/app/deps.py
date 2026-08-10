from __future__ import annotations

from dataclasses import dataclass, field

from app.config import Settings
from app.models.llm import LLMClient, OpenAILLMClient
from app.models.cooldown import CooldownStore, cooldown_path_for_kb, shared_cooldown_store
from app.models.catalog import set_active_models_dev_store
from app.models.models_dev import (
    ModelsDevStore,
    models_dev_cache_path_for_kb,
    shared_models_dev_store,
)
from app.storage.repo import KnowledgeRepo
from app.index.conversation_fts import ConversationFTS
from app.index.conversation_vector import ConversationVector
from app.index.revision import IndexRevision
from app.index.indexer import Indexer
from app.engine.retriever import Retriever
from app.engine.pending import PendingStore
from app.engine.merge_sessions import MergeSessionStore
from app.engine.conversations import ConversationStore
from app.engine.derivation_worker import DerivationWorker
from app.engine.memory.session_observe import SessionMemoryObserve
from app.engine.memory_maintenance import MemoryMaintenanceJob
from app.engine.pending_resolver import PendingResolver
from app.engine.merge_workflow import MergeWorkflow
from app.engine.organizer import Organizer
from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.chat.session_runner import ChatSessionRunner
from app.engine.agent.orchestrator import AgentOrchestrator
from app.engine.agent.system_layer import SystemLayer
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.engine.workspace import ensure_workspace_id

from app.deps_index import IndexSubgraph, build_index_subgraph
from app.deps_memory import MemorySubgraph, build_memory_subgraph
from app.deps_agent import AgentSubgraph, build_agent_subgraph
from app.engine.usage import UsageRecorder, UsageService, UsageStore


@dataclass
class Container:
    settings: Settings
    workspace_id: str
    llm: LLMClient
    model_cooldown: CooldownStore
    models_dev: ModelsDevStore
    usage: UsageService
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
    memory_worker: SessionMemoryObserve
    memory_maintenance: MemoryMaintenanceJob
    knowledge_writer: KnowledgeWriter
    merge_workflow: MergeWorkflow
    organizer: Organizer
    pending_resolver: PendingResolver
    agent: AgentOrchestrator
    chat_runner: ChatSessionRunner
    system_layer: SystemLayer
    memory_service: MemoryService
    _index_subgraph: IndexSubgraph | None = field(default=None, repr=False)
    _memory_subgraph: MemorySubgraph | None = field(default=None, repr=False)
    _agent_subgraph: AgentSubgraph | None = field(default=None, repr=False)
    _usage_store: UsageStore | None = field(default=None, repr=False)


def build_container(settings: Settings, llm: LLMClient | None = None) -> Container:
    workspace_id = ensure_workspace_id(settings.kb_path)
    usage_store = UsageStore(settings.kb_path / ".kb" / "usage" / "usage.db")
    usage_recorder = UsageRecorder(usage_store)
    usage = UsageService(usage_store)
    model_cooldown = shared_cooldown_store(cooldown_path_for_kb(settings.kb_path))
    models_dev = shared_models_dev_store(models_dev_cache_path_for_kb(settings.kb_path))
    set_active_models_dev_store(models_dev)
    llm = llm or OpenAILLMClient(
        settings, usage_recorder=usage_recorder, cooldown=model_cooldown
    )
    if isinstance(llm, OpenAILLMClient):
        if llm.usage_recorder is None:
            llm.usage_recorder = usage_recorder
        llm.cooldown = model_cooldown
    repo = KnowledgeRepo(settings.kb_path, protected_dirs=(settings.system_layer_dir,))

    memory_store = MemoryStore(
        settings.kb_path / ".kb" / "memory" / "memory.db",
        owner_key=workspace_id,
    )
    system_layer = SystemLayer(
        repo,
        dir_name=settings.system_layer_dir,
        precepts_filename=settings.precepts_filename,
        soul_filename=settings.soul_filename,
        memory_service=None,
    )

    index = build_index_subgraph(
        settings, repo, llm, system_layer_prefix=system_layer.prefix
    )
    knowledge_writer = KnowledgeWriter(repo, index.indexer)
    memory_service = MemoryService(
        memory_store,
        repo,
        conversations=None,
        knowledge_writer=knowledge_writer,
    )
    system_layer.memory_service = memory_service
    pending = PendingStore(settings.kb_path / ".kb" / "pending.json")
    merge_sessions = MergeSessionStore(
        settings.kb_path / ".kb" / "merge_sessions.json"
    )
    conversations = ConversationStore(
        settings.kb_path / ".kb" / "conversations"
    )

    memory = build_memory_subgraph(
        settings, repo, llm, conversations, memory_service=memory_service
    )

    derivation_worker = DerivationWorker(
        conversations,
        index.conversation_fts,
        conversation_vector=index.conversation_vector,
        llm=llm,
        index_revision=index.index_revision,
        chunk_chars=settings.conversation_chunk_chars,
        overlap=settings.conversation_chunk_overlap_chars,
    )
    memory.wire_conversations(conversations)

    agent = build_agent_subgraph(
        settings,
        llm,
        repo=repo,
        retriever=index.retriever,
        indexer=index.indexer,
        pending=pending,
        conversations=conversations,
        system_layer=system_layer,
        knowledge_writer=knowledge_writer,
        memory_service=memory.service,
    )

    pending_resolver = PendingResolver(
        pending=pending,
        organizer=agent.organizer,
        merge_workflow=agent.organizer.merge,
        conversations=conversations,
        merge_sessions=merge_sessions,
        sandbox_tools=agent.tools.sandbox,
    )

    return Container(
        settings=settings,
        workspace_id=workspace_id,
        llm=llm,
        model_cooldown=model_cooldown,
        models_dev=models_dev,
        usage=usage,
        repo=repo,
        indexer=index.indexer,
        retriever=index.retriever,
        pending=pending,
        merge_sessions=merge_sessions,
        conversations=conversations,
        conversation_fts=index.conversation_fts,
        conversation_vector=index.conversation_vector,
        index_revision=index.index_revision,
        derivation_worker=derivation_worker,
        memory_worker=memory.worker,
        memory_maintenance=memory.maintenance,
        knowledge_writer=knowledge_writer,
        merge_workflow=agent.organizer.merge,
        organizer=agent.organizer,
        pending_resolver=pending_resolver,
        agent=agent.agent,
        chat_runner=agent.chat_runner,
        system_layer=system_layer,
        memory_service=memory.service,
        _index_subgraph=index,
        _memory_subgraph=memory,
        _agent_subgraph=agent,
        _usage_store=usage_store,
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
    if container._usage_store is not None:
        try:
            container._usage_store.close()
        except Exception:
            pass
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
    set_active_models_dev_store(app.state.container.models_dev)
    app.state.auth_store = AuthStore(kb_path)
    app.state.session_store = SessionStore(kb_path)


def apply_settings(
    container: Container, settings: Settings, llm: LLMClient | None = None
) -> None:
    container.settings = settings
    recorder = None
    if container._usage_store is not None:
        recorder = UsageRecorder(container._usage_store)
    cooldown = container.model_cooldown
    if llm is None and isinstance(container.llm, OpenAILLMClient):
        container.llm.rebind_settings(settings)
        container.llm.cooldown = cooldown
        if container.llm.usage_recorder is None and recorder:
            container.llm.usage_recorder = recorder
        new_llm = container.llm
    else:
        new_llm = llm or OpenAILLMClient(
            settings, usage_recorder=recorder, cooldown=cooldown
        )
        if isinstance(new_llm, OpenAILLMClient):
            if new_llm.usage_recorder is None and recorder:
                new_llm.usage_recorder = recorder
            new_llm.cooldown = cooldown
    container.llm = new_llm
    if container._index_subgraph is not None:
        container._index_subgraph.apply_settings(settings)
        container._index_subgraph.rebind_llm(
            new_llm, derivation_worker=container.derivation_worker
        )
    if container._memory_subgraph is not None:
        container._memory_subgraph.rebind_llm(new_llm)
    if container._agent_subgraph is not None:
        container._agent_subgraph.rebind_llm(settings, new_llm)
        container._agent_subgraph.publish(container)
