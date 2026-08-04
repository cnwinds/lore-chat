from app.engine.conversations import ConversationStore


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


def test_iter_transcript_segments_splits_on_message_boundary(tmp_path):
    store = ConversationStore(tmp_path / "kb" / ".kb" / "conversations")
    cid = store.create()
    for i in range(5):
        t = store.begin_turn(
            cid,
            user_text=f"用户消息{i}" + ("×" * 200),
            client_message_id=f"c{i}",
            observation_allowed=False,
        )
        _finalize(store, cid, t["turn_id"], "回复")
    conv = store.get(cid)
    segments = list(ConversationStore.iter_transcript_segments(conv, max_chars=500))
    assert len(segments) >= 2
    for seg in segments:
        assert seg["messages"]
        assert seg["first_message_id"] != seg["last_message_id"] or len(seg["messages"]) == 1


def test_summarize_long_conversation_calls_merge(tmp_path):
    from app.config import Settings
    from app.engine.organizer import Organizer
    from app.engine.pending import PendingStore
    from app.engine.retriever import Retriever
    from app.index.fulltext import FullTextIndex
    from app.index.indexer import Indexer
    from app.index.vector import VectorIndex
    from app.models.llm import FakeLLMClient
    from app.storage.repo import KnowledgeRepo
    from tests.helpers import make_writer

    calls: list[int] = []

    class CountingLLM(FakeLLMClient):
        def chat(self, messages, big=False):
            calls.append(len(messages))
            return "段摘要或终稿\n"

    store = ConversationStore(tmp_path / "kb" / ".kb" / "conversations")
    cid = store.create()
    for i in range(8):
        t = store.begin_turn(
            cid,
            user_text="内容" + ("长" * 4000),
            client_message_id=f"c{i}",
            observation_allowed=False,
        )
        _finalize(store, cid, t["turn_id"], "收到")
    conv = store.get(cid)
    llm = CountingLLM(chat_responses=[], embed_dim=8)
    repo = KnowledgeRepo(tmp_path / "kb", protected_dirs=("系统",))
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    org = Organizer(
        repo=repo,
        retriever=Retriever(vi, fi, llm),
        indexer=Indexer(vi, fi, llm),
        pending=PendingStore(tmp_path / "pending.json"),
        llm=llm,
        settings=Settings(summarize_segment_chars=5000),
        knowledge_writer=make_writer(repo, tmp_path),
    )
    transcript = ConversationStore.full_transcript(conv)
    assert len(transcript) > 5000
    result = org.summarize_conversation(
        transcript, conv=conv, conversation_id=cid, system_rules=""
    )
    assert result.status == "saved"
    assert len(calls) >= 2
