"""ContextViewTools 测试共用 fixture。"""

from __future__ import annotations

import pytest

from app.engine.agent.tool_impl.context_view_tools import ContextViewTools
from app.engine.agent.tool_impl.doc_read_guard import DocReadGuard
from app.engine.channel_plugins.store import ChannelInstanceStore
from app.engine.conversations import ConversationStore
from app.engine.disclosure import DisclosureWindows
from app.engine.memory.cards import KnowledgeCards
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.engine.organizer import Organizer
from app.engine.pending import PendingStore
from app.engine.retriever import Retriever
from app.engine.roles import RoleStore
from app.index.indexer import Indexer
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_conversation_index, make_writer


@pytest.fixture
def cv_env(tmp_path):
    kb = tmp_path / "knowledge"
    kb.mkdir(exist_ok=True)
    llm = FakeLLMClient(embed_dim=8)
    roles = RoleStore(tmp_path / "roles")
    conv = ConversationStore(tmp_path / "conversations")
    repo = KnowledgeRepo(kb, protected_dirs=("系统",))
    ci = make_conversation_index(tmp_path, llm)
    si = ci.search_index
    writer = make_writer(repo, tmp_path, embed_dim=8)
    writer.indexer = Indexer(si)
    idx = writer.indexer
    retr = Retriever(si, llm)
    owner = MemoryService(
        MemoryStore(tmp_path / "memory.db", owner_key="ws1"),
        repo,
        knowledge_writer=writer,
    )
    channel_instances = ChannelInstanceStore(kb)
    cards = KnowledgeCards(
        tmp_path / "memory.db",
        owner=owner,
        roles=roles,
        conversations=conv,
        channel_instances=channel_instances,
    )
    tools = ContextViewTools(
        repo=repo,
        retriever=retr,
        conversations=conv,
        roles=roles,
        read_guard=DocReadGuard(require_read=True),
        disclosure_windows=DisclosureWindows(),
        memory_service=owner,
        cards=cards,
        channel_instances=channel_instances,
    )
    pending = PendingStore(kb / ".kb" / "pending.json")
    org = Organizer(
        repo=repo,
        retriever=retr,
        pending=pending,
        llm=llm,
        knowledge_writer=writer,
    )
    return type(
        "CvEnv",
        (),
        {
            "tools": tools,
            "repo": repo,
            "writer": writer,
            "idx": idx,
            "retr": retr,
            "roles": roles,
            "conv": conv,
            "cards": cards,
            "owner": owner,
            "channel_instances": channel_instances,
            "llm": llm,
            "org": org,
            "ci": ci,
        },
    )()
