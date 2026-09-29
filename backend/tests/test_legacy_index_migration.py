"""旧 kbs 向量集合迁入分区底座（文档库部分）。"""

import app.index.legacy_migration as legacy_migration
from app.backup.reindex import _reindex_kb_files, reindex_all
from app.config import Settings
from app.deps import build_container
from app.index.chroma_client import make_persistent_client
from app.index.kb_index import KB_PARTITION
from app.index.conversation_index import CONV_PARTITION
from app.index.legacy_migration import (
    META_CONV_MIGRATED,
    META_KB_MIGRATED,
    migrate_legacy_indexes,
)
from app.index.message_chunk import MessageChunk
from app.models.llm import FakeLLMClient
from tests.helpers import drain_embeddings

_LEGACY_KB = "kbs"
_LEGACY_CONV = "conversation_chunks_v2"
_CHROMA_META = {"hnsw:space": "cosine"}


def _add_legacy_kb_doc(vec_dir, doc_id, chunks, embeddings, *, source):
    vec_dir.mkdir(parents=True, exist_ok=True)
    col = make_persistent_client(str(vec_dir)).get_or_create_collection(
        _LEGACY_KB, metadata=_CHROMA_META
    )
    ids = [f"{doc_id}::{i}" for i in range(len(chunks))]
    metadatas = [{"doc_id": doc_id, "source": source} for _ in chunks]
    col.add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)


def _add_legacy_conv_message(
    vec_dir,
    *,
    conversation_id,
    message_id,
    role,
    ts,
    conversation_title,
    chunks,
    embeddings,
):
    vec_dir.mkdir(parents=True, exist_ok=True)
    col = make_persistent_client(str(vec_dir)).get_or_create_collection(
        _LEGACY_CONV, metadata=_CHROMA_META
    )
    ids, docs, metas = [], [], []
    for c, emb in zip(chunks, embeddings):
        item_id = f"conv:{conversation_id}:msg:{message_id}:chunk:{c.index}"
        ids.append(item_id)
        docs.append(c.text)
        metas.append(
            {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "role": role,
                "chunk_index": c.index,
                "start_char": c.start_char,
                "end_char": c.end_char,
                "ts": ts,
                "conversation_title": conversation_title or "",
            }
        )
    col.add(ids=ids, documents=docs, embeddings=embeddings, metadatas=metas)


def _skip_conv_migration(si) -> None:
    si.set_meta(META_CONV_MIGRATED, "2026-01-01T00:00:00+00:00")


class CountingLLM(FakeLLMClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.embed_calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        return super().embed(texts)

    def embed_with_model(self, texts: list[str]):
        self.embed_calls += len(texts)
        return self.embed(texts), f"fake-embed-{self.embed_dim}"


def test_adopts_matching_legacy_vectors_without_re_embed(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    (kb_path / "doc.md").write_text("legacy body text for adopt", encoding="utf-8")
    index_dir = kb_path / ".kb" / "index"
    index_dir.mkdir(parents=True)

    llm = CountingLLM(embed_dim=8)
    settings = Settings(kb_path=kb_path)
    container = build_container(settings, llm=llm)
    si = container.search_index
    _skip_conv_migration(si)

    chunks = ["legacy body text for adopt"]
    embs = llm.embed(chunks)
    _add_legacy_kb_doc(index_dir / "vec", "doc.md", chunks, embs, source="doc.md")

    llm.embed_calls = 0
    stats = migrate_legacy_indexes(container)
    assert stats["kb_adopted"] == 1
    assert stats["kb_docs"] >= 1
    assert llm.embed_calls == 1

    row = si._lexical.get_item(KB_PARTITION, "doc.md::0")
    assert row is not None
    assert row["vec_state"] == "ok"


def test_migrate_partial_adopt_when_file_changed(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    (kb_path / "keep.md").write_text("unchanged body alpha", encoding="utf-8")
    (kb_path / "changed.md").write_text("new body on disk beta", encoding="utf-8")
    index_dir = kb_path / ".kb" / "index"
    index_dir.mkdir(parents=True)

    llm = CountingLLM(embed_dim=8)
    settings = Settings(kb_path=kb_path)
    container = build_container(settings, llm=llm)
    si = container.search_index
    _skip_conv_migration(si)

    vec_dir = index_dir / "vec"
    _add_legacy_kb_doc(
        vec_dir,
        "keep.md",
        ["unchanged body alpha"],
        llm.embed(["unchanged body alpha"]),
        source="keep.md",
    )
    _add_legacy_kb_doc(
        vec_dir,
        "changed.md",
        ["old body before edit"],
        llm.embed(["old body before edit"]),
        source="changed.md",
    )

    llm.embed_calls = 0
    stats = migrate_legacy_indexes(container)
    assert stats["kb_adopted"] == 1
    assert llm.embed_calls == 1

    keep_row = si._lexical.get_item(KB_PARTITION, "keep.md::0")
    changed_row = si._lexical.get_item(KB_PARTITION, "changed.md::0")
    assert keep_row["vec_state"] == "ok"
    assert changed_row["vec_state"] == "pending"

    llm.embed_calls = 0
    drain_embeddings(si)
    assert llm.embed_calls == 1


def test_second_migration_skipped_when_marker_set(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    index_dir = kb_path / ".kb" / "index"
    index_dir.mkdir(parents=True)
    settings = Settings(kb_path=kb_path)
    container = build_container(settings, llm=FakeLLMClient(embed_dim=8))
    container.search_index.set_meta(META_KB_MIGRATED, "2026-01-01T00:00:00+00:00")

    stats = migrate_legacy_indexes(container)
    assert stats["kb_skipped"] is True
    assert stats["kb_adopted"] == 0


def test_probe_failure_no_adopt(tmp_path, monkeypatch):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    (kb_path / "doc.md").write_text("text", encoding="utf-8")
    settings = Settings(kb_path=kb_path)
    llm = CountingLLM(embed_dim=8)
    container = build_container(settings, llm=llm)
    si = container.search_index
    _skip_conv_migration(si)

    vec_dir = kb_path / ".kb" / "index" / "vec"
    _add_legacy_kb_doc(
        vec_dir, "doc.md", ["text"], llm.embed(["text"]), source="doc.md"
    )

    monkeypatch.setattr(si, "probe_model", lambda: None)
    llm.embed_calls = 0
    stats = migrate_legacy_indexes(container)
    assert stats["kb_adopted"] == 0
    assert llm.embed_calls == 0
    row = si._lexical.get_item(KB_PARTITION, "doc.md::0")
    assert row is not None
    assert row["vec_state"] == "pending"


def test_missing_legacy_collection_no_error(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    settings = Settings(kb_path=kb_path)
    container = build_container(settings, llm=FakeLLMClient(embed_dim=8))
    stats = migrate_legacy_indexes(container)
    assert stats["kb_skipped"] is False
    assert stats["kb_adopted"] == 0
    assert container.search_index.get_meta(META_KB_MIGRATED) is not None


def test_embed_pending_blocked_during_kb_migration(tmp_path, monkeypatch):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    (kb_path / "keep.md").write_text("unchanged held alpha", encoding="utf-8")
    (kb_path / "changed.md").write_text("new held beta", encoding="utf-8")
    settings = Settings(kb_path=kb_path)
    llm = FakeLLMClient(embed_dim=8)
    container = build_container(settings, llm=llm)
    si = container.search_index
    _skip_conv_migration(si)

    vec_dir = kb_path / ".kb" / "index" / "vec"
    _add_legacy_kb_doc(
        vec_dir,
        "keep.md",
        ["unchanged held alpha"],
        llm.embed(["unchanged held alpha"]),
        source="keep.md",
    )
    _add_legacy_kb_doc(
        vec_dir,
        "changed.md",
        ["old held gamma"],
        llm.embed(["old held gamma"]),
        source="changed.md",
    )

    embed_during_probe: list[int] = []
    real_probe = si.probe_model

    def probe_with_embed_check():
        embed_during_probe.append(si.embed_pending(32))
        return real_probe()

    monkeypatch.setattr(si, "probe_model", probe_with_embed_check)
    migrate_legacy_indexes(container)

    assert embed_during_probe
    assert embed_during_probe[0] == 0
    assert si._lexical.get_item(KB_PARTITION, "changed.md::0")["vec_state"] == "pending"
    assert si.embed_pending(32) > 0


def test_adopt_client_open_failure_no_marker(tmp_path, monkeypatch):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    (kb_path / "doc.md").write_text("text", encoding="utf-8")
    settings = Settings(kb_path=kb_path)
    llm = FakeLLMClient(embed_dim=8)
    container = build_container(settings, llm=llm)
    _skip_conv_migration(container.search_index)

    vec_dir = kb_path / ".kb" / "index" / "vec"
    _add_legacy_kb_doc(
        vec_dir, "doc.md", ["text"], llm.embed(["text"]), source="doc.md"
    )

    def _fail_client(_path):
        raise OSError("chroma unavailable")

    monkeypatch.setattr(legacy_migration, "make_persistent_client", _fail_client)
    stats = migrate_legacy_indexes(container)
    assert stats["kb_docs"] == 0
    assert stats["kb_adopted"] == 0
    assert container.search_index.get_meta(META_KB_MIGRATED) is None


def test_reindex_kb_files_alone_does_not_set_marker(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    (kb_path / "a.md").write_text("hello\n", encoding="utf-8")
    settings = Settings(kb_path=kb_path)
    container = build_container(settings, llm=FakeLLMClient(embed_dim=8))

    n = _reindex_kb_files(container)
    assert n >= 1
    assert container.search_index.get_meta(META_KB_MIGRATED) is None


def test_reindex_all_sets_migration_marker(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    (kb_path / "a.md").write_text("hello\n", encoding="utf-8")
    settings = Settings(kb_path=kb_path)
    container = build_container(settings, llm=FakeLLMClient(embed_dim=8))

    result = reindex_all(container)
    assert result["ok"] is True
    assert container.search_index.get_meta(META_KB_MIGRATED) is not None
    assert container.search_index.get_meta(META_CONV_MIGRATED) is not None


def test_conv_legacy_vector_adopted(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    settings = Settings(kb_path=kb_path)
    llm = CountingLLM(embed_dim=8)
    container = build_container(settings, llm=llm)
    si = container.search_index
    si.set_meta(META_KB_MIGRATED, "done")

    store = container.conversations
    cid = store.create()
    body = "adopt me please"
    turn = store.begin_turn(cid, body, "c1", observation_allowed=False)
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={"text": "ok", "timeline": [], "sources": [], "status": "complete"},
    )
    msg_id = store.conn.execute(
        "SELECT id FROM messages WHERE conversation_id=? LIMIT 1", (cid,)
    ).fetchone()[0]

    from app.index.message_chunk import chunk_message

    chunks = chunk_message(body, size=1000, overlap=150)
    assert chunks
    _add_legacy_conv_message(
        kb_path / ".kb" / "index" / "vec",
        conversation_id=cid,
        message_id=msg_id,
        role="user",
        ts="t",
        conversation_title="",
        chunks=chunks,
        embeddings=llm.embed([c.text for c in chunks]),
    )

    llm.embed_calls = 0
    stats = migrate_legacy_indexes(container)
    assert stats["conv_adopted"] >= 1
    assert llm.embed_calls == 1
    row = si._lexical.get_item(
        CONV_PARTITION,
        f"conv:{cid}:msg:{msg_id}:chunk:0",
    )
    assert row["vec_state"] == "ok"


def test_conv_migration_skips_deleted_conversation(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    settings = Settings(kb_path=kb_path)
    container = build_container(settings, llm=FakeLLMClient(embed_dim=8))
    container.search_index.set_meta(META_KB_MIGRATED, "done")

    ledger = kb_path / ".kb" / "migrations" / "conversation-deletions.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text('{"conversation_id": "deleted-cid"}\n', encoding="utf-8")

    chunk = MessageChunk(0, 0, 4, "gone")
    _add_legacy_conv_message(
        kb_path / ".kb" / "index" / "vec",
        conversation_id="deleted-cid",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[chunk],
        embeddings=[[0.1] * 8],
    )

    migrate_legacy_indexes(container)
    assert "deleted-cid" not in container.conversation_index.conversation_ids()


def test_conv_migration_marker_skips_second_run(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    settings = Settings(kb_path=kb_path)
    container = build_container(settings, llm=FakeLLMClient(embed_dim=8))
    container.search_index.set_meta(META_KB_MIGRATED, "done")
    container.search_index.set_meta(META_CONV_MIGRATED, "2026-01-01T00:00:00+00:00")
    stats = migrate_legacy_indexes(container)
    assert stats["conv_skipped"] is True


def test_kb_failure_does_not_block_conv_migration(tmp_path, monkeypatch):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    settings = Settings(kb_path=kb_path)
    container = build_container(settings, llm=FakeLLMClient(embed_dim=8))
    cid = container.conversations.create()
    container.conversations.begin_turn(cid, "hi", "c1", observation_allowed=False)

    monkeypatch.setattr(legacy_migration, "_migrate_kb", lambda *a, **k: None)
    migrate_legacy_indexes(container)
    assert container.search_index.get_meta(META_KB_MIGRATED) is None
    assert container.search_index.get_meta(META_CONV_MIGRATED) is not None
