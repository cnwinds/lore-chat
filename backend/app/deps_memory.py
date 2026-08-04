from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.engine.conversations import ConversationStore
from app.engine.memory.decay import DecayConfig
from app.engine.memory.llm_extractor import LLMMemoryExtractor
from app.engine.memory.observer import MemoryObserver
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.engine.memory_maintenance import MemoryMaintenanceJob
from app.engine.memory_worker import MemoryWorker
from app.engine.knowledge_writer import KnowledgeWriter
from app.models.llm import LLMClient
from app.storage.repo import KnowledgeRepo


@dataclass
class MemorySubgraph:
    store: MemoryStore
    service: MemoryService
    worker: MemoryWorker
    maintenance: MemoryMaintenanceJob

    def wire_conversations(self, conversations: ConversationStore) -> None:
        self.service.conversations = conversations

    def wire_knowledge_writer(self, writer: KnowledgeWriter) -> None:
        self.service.knowledge_writer = writer

    def rebind_llm(self, llm: LLMClient) -> None:
        self.worker.observer.extractor = LLMMemoryExtractor(llm)


def build_memory_subgraph(
    settings: Settings,
    repo: KnowledgeRepo,
    llm: LLMClient,
    conversations: ConversationStore,
    *,
    memory_service: MemoryService,
) -> MemorySubgraph:
    memory_store = memory_service.store
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
    return MemorySubgraph(
        store=memory_store,
        service=memory_service,
        worker=memory_worker,
        maintenance=memory_maintenance,
    )
