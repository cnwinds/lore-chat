from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.engine.conversations import ConversationStore
from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.memory.resolver import SlotAction
from app.engine.memory.service import MemoryService
from app.engine.memory.session_extractor import SessionMemoryExtractor
from app.engine.memory.store import MemoryStore
from app.engine.memory_worker import MemoryWorker
from app.index.conversation_index import CONV_FAMILY, CONV_PARTITION, ConversationIndex
from app.index.indexer import Indexer
from app.index.partitioned import (
    LLMEmbedder,
    PartitionTuning,
    SearchIndex,
)
from app.index.search_query import compile_search_query
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo


def make_conversation_index(tmp_path, llm=None) -> ConversationIndex:
    return ConversationIndex(make_search_index(tmp_path, llm))


def conv_fts_hits(search_index: SearchIndex, query: str, *, k: int = 5) -> list:
    compiled = compile_search_query(query)
    res = search_index.search(
        query,
        partitions=[CONV_PARTITION],
        limit=k,
        tunings={CONV_FAMILY: PartitionTuning(fts_k=k, vec_k=k)},
        fts_mode="keywords",
        vector_text=compiled.vector_text,
        lanes=("fts",),
    )
    return res.lanes.get(f"{CONV_FAMILY}:fts", [])


def make_search_index(tmp_path, llm=None) -> SearchIndex:
    llm = llm or FakeLLMClient(embed_dim=8)
    return SearchIndex(
        tmp_path / "partitioned.db",
        tmp_path / "vec",
        LLMEmbedder(llm),
    )


def drain_embeddings(search_index: SearchIndex) -> None:
    while search_index.embed_pending(256) > 0:
        pass


def make_writer(repo: KnowledgeRepo, tmp_path, *, embed_dim: int = 8) -> KnowledgeWriter:
    llm = FakeLLMClient(embed_dim=embed_dim)
    search_index = make_search_index(tmp_path, llm)
    idx = Indexer(search_index, system_prefixes=("系统/",))
    return KnowledgeWriter(repo, idx)


def scripted_memory_extractor(*actions: SlotAction):
    """测试替身：固定返回 SlotAction，不走启发式/LLM。"""

    class _Scripted:
        def extract(self, _messages, *, confirmed_summary):
            del confirmed_summary
            return list(actions)

    return _Scripted()


def preference_action(
    statement: str,
    *,
    slot_key: str = "preference.response_style",
    action: str = "new",
) -> SlotAction:
    return SlotAction(
        slot_key=slot_key,
        action=action,
        statement=statement,
        category="preference",
        origin="direct",
        confidence=0.9,
    )


@dataclass
class IdleObserveFixture:
    conv: ConversationStore
    mem: MemoryStore
    svc: MemoryService
    worker: MemoryWorker
    cid: str

    def memory_dirty(self) -> int:
        row = self.conv.conn.execute(
            "SELECT memory_dirty FROM conversations WHERE id = ?",
            (self.cid,),
        ).fetchone()
        return int(row["memory_dirty"] or 0)


def make_idle_observe_fixture(
    tmp_path,
    *,
    extractor: SessionMemoryExtractor | None,
    user_text: str = "我偏好简洁回答",
    idle_hours: float = 0,
) -> IdleObserveFixture:
    """空闲会话 + worker，供 dirty 保留/清除类用例共用。"""
    conv = ConversationStore(tmp_path / "conversations")
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    mem = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    svc = MemoryService(mem, repo, knowledge_writer=make_writer(repo, tmp_path))
    worker = MemoryWorker(conv, svc, extractor=extractor, idle_hours=idle_hours)
    cid = conv.create()
    conv.begin_turn(cid, user_text, "c1", observation_allowed=True)
    past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    conv.conn.execute(
        "UPDATE conversations SET last_user_message_at = ? WHERE id = ?",
        (past, cid),
    )
    conv.conn.commit()
    return IdleObserveFixture(conv=conv, mem=mem, svc=svc, worker=worker, cid=cid)
