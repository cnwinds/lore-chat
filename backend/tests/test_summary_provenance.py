from app.engine.conversations import ConversationStore
from app.engine.organizer import Organizer, PlacementDecision
from app.engine.pending import PendingStore
from app.engine.retriever import Retriever
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


def _finalize(store, cid, turn_id, text):
    store.finalize_turn(
        cid,
        turn_id=turn_id,
        assistant={
            "text": text,
            "timeline": [],
            "sources": [],
            "status": "complete",
        },
    )


def test_get_conversation_includes_summaries_array(tmp_path):
    store = ConversationStore(tmp_path / "kb" / ".kb" / "conversations")
    cid = store.create()
    store.mark_summarized(cid, "娱乐/盘点.md")
    conv = store.get(cid)
    assert "summaries" in conv
    assert len(conv["summaries"]) == 1
    assert conv["summaries"][0]["doc_path"] == "娱乐/盘点.md"
    assert conv["summaries"][0]["status"] == "current"
    assert conv["summary_path"] == "娱乐/盘点.md"  # 兼容


def test_append_message_marks_summary_stale(tmp_path):
    store = ConversationStore(tmp_path / "kb" / ".kb" / "conversations")
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="first", client_message_id="c1", observation_allowed=False
    )
    _finalize(store, cid, turn["turn_id"], "ok")
    store.mark_summarized(cid, "娱乐/盘点.md")
    store.begin_turn(cid, user_text="second", client_message_id="c2", observation_allowed=False)
    summaries = store.list_summaries(cid)
    assert any(s["status"] == "stale" for s in summaries)


def test_organizer_writes_conversation_ids_list(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    llm = FakeLLMClient(chat_responses=["# 标题\n\n正文"], embed_dim=8)
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    org = Organizer(
        repo=repo,
        retriever=Retriever(vi, fi, llm),
        pending=PendingStore(tmp_path / "pending.json"),
        llm=llm,
        knowledge_writer=make_writer(repo, tmp_path),
    )
    decision = PlacementDecision(
        action="new",
        rel_path="娱乐/盘点.md",
        title="盘点",
        category="娱乐",
        tags=[],
        ambiguous=False,
        reason="test",
    )
    org._apply(decision, "正文\n", conversation_id="cid-abc")
    doc = repo.read_doc("娱乐/盘点.md")
    assert doc.meta.get("conversation_ids") == ["cid-abc"]
    assert "conversation_id" not in doc.meta
