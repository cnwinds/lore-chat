from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.engine.agent.orchestrator import AgentOrchestrator
from app.engine.agent.system_layer import SystemLayer
from app.engine.agent.tools import ToolRegistry
from app.engine.chat.session_runner import ChatSessionRunner
from app.engine.conversations import ConversationStore
from app.engine.disclosure import DisclosureWindows
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
from app.engine.imagegen import ImageGen
from app.engine.sandbox.factory import build_sandbox_pool
from app.models.cooldown import CooldownStore
from app.models.llm import LLMClient
from app.storage.repo import KnowledgeRepo


@dataclass
class AgentSubgraph:
    organizer: Organizer
    tools: ToolRegistry
    agent: AgentOrchestrator
    chat_runner: ChatSessionRunner
    search_cooldown: CooldownStore
    image_cooldown: CooldownStore
    room_delivery: object | None = None

    def publish(self, container) -> None:
        """将子图运行时指针同步到 Container / PendingResolver facade。"""
        container.chat_runner = self.chat_runner
        container.room_delivery = self.room_delivery
        container.agent = self.agent
        container.organizer = self.organizer
        container.merge_workflow = self.organizer.merge
        container.pending_resolver.organizer = self.organizer
        container.pending_resolver.merge_workflow = self.organizer.merge
        container.pending_resolver.sandbox_tools = self.tools.sandbox

    def rebind_llm(
        self,
        settings: Settings,
        llm: LLMClient,
        *,
        search_cooldown: CooldownStore,
        image_cooldown: CooldownStore,
    ) -> None:
        self.organizer.llm = llm
        self.organizer.synthesis.llm = llm
        self.organizer.merge.llm = llm
        self.organizer.merge.synthesis = self.organizer.synthesis
        self.agent.settings = settings
        self.agent.llm = llm
        self.search_cooldown = search_cooldown
        self.image_cooldown = image_cooldown
        image_gen = ImageGen(
            settings,
            cooldown=image_cooldown,
            knowledge_writer=self.tools.knowledge_writer,
        )
        self.agent.tools.rebind(
            web_search=WebSearch(settings, cooldown=search_cooldown),
            fetcher=WebFetcher(
                settings.fetch_url_timeout,
                settings.fetch_url_max_bytes,
                settings.fetch_url_pdf_max_bytes,
            ),
            web_search_default_k=settings.web_search_default_k,
            image_gen=image_gen,
        )
        from app.engine.sandbox.factory import apply_sandbox_settings

        apply_sandbox_settings(
            settings,
            pool=getattr(self.agent.tools, "sandbox_pool", None)
            or getattr(self.agent.tools.sandbox, "pool", None),
            runtime=self.agent.tools.sandbox_runtime
            or getattr(self.agent.tools.sandbox, "runtime", None),
            sandbox_tools=self.agent.tools.sandbox,
        )
        hub = self.chat_runner.turn_hub
        hub.agent = self.agent
        self.chat_runner = ChatSessionRunner(
            self.agent,
            self.chat_runner.conversations,
            inject_broker=self.chat_runner.inject_broker,
            turn_hub=hub,
            roles=getattr(self.chat_runner, "roles", None),
        )
        if self.room_delivery is not None:
            self.room_delivery.settings = settings
            self.room_delivery.bind_starter(self.chat_runner.begin_persisted_turn)


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
    search_cooldown: CooldownStore,
    image_cooldown: CooldownStore,
    enabled_skills=None,
    roles=None,
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
    fetcher = WebFetcher(
        settings.fetch_url_timeout,
        settings.fetch_url_max_bytes,
        settings.fetch_url_pdf_max_bytes,
    )
    web_search = WebSearch(settings, cooldown=search_cooldown)
    image_gen = ImageGen(
        settings, cooldown=image_cooldown, knowledge_writer=knowledge_writer
    )
    sandbox_pool = build_sandbox_pool(settings)
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
        disclosure_windows=DisclosureWindows(
            spot=settings.read_disclosure_chars,
            deep=settings.read_disclosure_deep_chars,
            max_chars=settings.read_disclosure_max_chars,
        ),
        edit_doc_max_edits=settings.edit_doc_max_edits,
        edit_doc_max_patch_chars=settings.edit_doc_max_patch_chars,
        edit_doc_require_read=settings.edit_doc_require_read,
        conversation_context_max_chars=settings.conversation_context_max_chars,
        web_search_default_k=settings.web_search_default_k,
        memory_service=memory_service,
        sandbox_pool=sandbox_pool,
        image_gen=image_gen,
        roles=roles,
    )
    from app.engine.sandbox.factory import apply_sandbox_settings

    apply_sandbox_settings(
        settings,
        pool=sandbox_pool,
        sandbox_tools=tool_registry.sandbox,
    )
    agent = AgentOrchestrator(
        settings,
        llm,
        tool_registry,
        system_layer=system_layer,
    )
    chat_runner = ChatSessionRunner(
        agent, conversations, enabled_skills=enabled_skills, roles=roles
    )
    from app.engine.rooms.delivery import RoomDelivery

    room_delivery = RoomDelivery(
        conversations, roles, settings=settings, pending=pending
    )
    room_delivery.bind_starter(chat_runner.begin_persisted_turn)
    tool_registry.roles_tools.delivery = room_delivery
    conversations._after_turn_finalized = room_delivery.drain_role
    return AgentSubgraph(
        organizer=organizer,
        tools=tool_registry,
        agent=agent,
        chat_runner=chat_runner,
        search_cooldown=search_cooldown,
        image_cooldown=image_cooldown,
        room_delivery=room_delivery,
    )
