from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.engine.agent.orchestrator import AgentOrchestrator
from app.engine.agent.system_layer import SystemLayer
from app.engine.agent.tools import ToolRegistry
from app.engine.chat.session_runner import ChatSessionRunner
from app.engine.conversations import ConversationStore
from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.merge_workflow import MergeWorkflow
from app.engine.organizer import Organizer
from app.engine.placement import PlacementPlanner
from app.engine.pending import PendingStore
from app.engine.retriever import Retriever
from app.index.indexer import Indexer
from app.engine.memory.service import MemoryService
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import WebSearch
from app.models.llm import LLMClient
from app.storage.repo import KnowledgeRepo


@dataclass
class AgentSubgraph:
    organizer: Organizer
    tools: ToolRegistry
    agent: AgentOrchestrator
    chat_runner: ChatSessionRunner

    def rebind_llm(self, settings: Settings, llm: LLMClient) -> None:
        self.organizer.llm = llm
        self.organizer.synthesis.llm = llm
        self.organizer.merge.llm = llm
        self.organizer.merge.synthesis = self.organizer.synthesis
        self.agent.settings = settings
        self.agent.llm = llm
        self.agent.tools.web_search = WebSearch(settings)
        self.agent.tools.fetcher = WebFetcher(
            settings.fetch_url_timeout, settings.fetch_url_max_bytes
        )
        self.chat_runner = ChatSessionRunner(
            self.agent,
            self.chat_runner.conversations,
            inject_broker=self.chat_runner.inject_broker,
        )


def build_agent_subgraph(
    settings: Settings,
    llm: LLMClient,
    *,
    repo: KnowledgeRepo,
    retriever: Retriever,
    indexer: Indexer,
    pending: PendingStore,
    conversations: ConversationStore,
    system_layer: SystemLayer,
    knowledge_writer: KnowledgeWriter,
    memory_service: MemoryService,
) -> AgentSubgraph:
    planner_host = PlacementPlanner(repo, retriever, llm)
    merge_workflow = MergeWorkflow(
        repo=repo,
        retriever=retriever,
        llm=llm,
        writer=knowledge_writer,
        planner=planner_host,
        pending=pending,
    )
    organizer = Organizer(
        repo=repo,
        retriever=retriever,
        pending=pending,
        llm=llm,
        knowledge_writer=knowledge_writer,
        planner=planner_host,
        merge_workflow=merge_workflow,
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
        knowledge_writer,
        conversations=conversations,
        system_layer=system_layer,
        indexer=indexer,
        disclosure_chars=settings.read_disclosure_chars,
        edit_doc_max_edits=settings.edit_doc_max_edits,
        edit_doc_max_patch_chars=settings.edit_doc_max_patch_chars,
        edit_doc_require_read=settings.edit_doc_require_read,
        conversation_context_max_chars=settings.conversation_context_max_chars,
        memory_service=memory_service,
    )
    agent = AgentOrchestrator(settings, llm, tool_registry, system_layer=system_layer)
    chat_runner = ChatSessionRunner(agent, conversations)
    return AgentSubgraph(
        organizer=organizer,
        tools=tool_registry,
        agent=agent,
        chat_runner=chat_runner,
    )
