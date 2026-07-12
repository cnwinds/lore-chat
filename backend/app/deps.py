from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.models.llm import LLMClient, OpenAILLMClient
from app.storage.repo import KnowledgeRepo
from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.engine.retriever import Retriever
from app.engine.pending import PendingStore
from app.engine.merge_sessions import MergeSessionStore
from app.engine.conversations import ConversationStore
from app.engine.organizer import Organizer
from app.engine.agent.orchestrator import AgentOrchestrator
from app.engine.agent.system_layer import SystemLayer
from app.engine.agent.tools import ToolRegistry
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import WebSearch


@dataclass
class Container:
    settings: Settings
    llm: LLMClient
    repo: KnowledgeRepo
    indexer: Indexer
    retriever: Retriever
    pending: PendingStore
    merge_sessions: MergeSessionStore
    conversations: ConversationStore
    organizer: Organizer
    agent: AgentOrchestrator
    system_layer: SystemLayer


def build_container(settings: Settings, llm: LLMClient | None = None) -> Container:
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
    indexer = Indexer(vector, fulltext, llm)
    retriever = Retriever(
        vector,
        fulltext,
        llm,
        excluded_prefixes=(system_layer.prefix,),
        min_score=settings.min_vector_score,
    )
    pending = PendingStore(settings.kb_path / ".kb" / "pending.json")
    merge_sessions = MergeSessionStore(
        settings.kb_path / ".kb" / "merge_sessions.json"
    )
    conversations = ConversationStore(
        settings.kb_path / ".kb" / "conversations"
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
    )
    agent = AgentOrchestrator(settings, llm, tool_registry, system_layer=system_layer)
    return Container(
        settings=settings,
        llm=llm,
        repo=repo,
        indexer=indexer,
        retriever=retriever,
        pending=pending,
        merge_sessions=merge_sessions,
        conversations=conversations,
        organizer=organizer,
        agent=agent,
        system_layer=system_layer,
    )
