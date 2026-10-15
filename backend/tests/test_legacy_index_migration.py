"""旧栈全文迁入分区底座；向量不沿用，由后台重嵌（ADR 2026-10-15）。"""

import app.index.legacy_migration as legacy_migration
from app.backup.reindex import _reindex_kb_files, reindex_all
from app.config import Settings
from app.deps import build_container
from app.index.conversation_index import CONV_PARTITION
from app.index.kb_index import KB_PARTITION
from app.index.legacy_migration import (
    META_CONV_MIGRATED,
    META_KB_MIGRATED,
    migrate_legacy_indexes,
)
from app.models.llm import FakeLLMClient
from tests.helpers import drain_embeddings


def _skip_conv_migration(si) -> None:
    si.set_meta(META_CONV_MIGRATED, "2026-01-01T00:00:00+00:00")


def test_kb_migration_rebuilds_text_and_leaves_vectors_pending(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    (kb_path / "doc.md").write_text("legacy body text", encoding="utf-8")
    container = build_container(Settings(kb_path=kb_path), llm=FakeLLMClient(embed_dim=8))
    si = container.search_index
    _skip_conv_migration(si)

    stats = migrate_legacy_indexes(container)
    assert stats["kb_docs"] >= 1
    assert si.get_meta(META_KB_MIGRATED) is not None
    row = si._lexical.get_item(KB_PARTITION, "doc.md::0")
    assert row is not None
    assert row["vec_state"] == "pending"

    drain_embeddings(si)
    assert si._lexical.get_item(KB_PARTITION, "doc.md::0")["vec_state"] == "ok"


def test_build_container_removes_legacy_vector_dir(tmp_path):
    kb_path = tmp_path / "knowledge"
    vec_dir = kb_path / ".kb" / "index" / "vec"
    vec_dir.mkdir(parents=True)
    (vec_dir / "chroma.sqlite3").write_bytes(b"legacy")
    build_container(Settings(kb_path=kb_path), llm=FakeLLMClient(embed_dim=8))
    assert not vec_dir.exists()


def test_second_migration_skipped_when_marker_set(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    container = build_container(Settings(kb_path=kb_path), llm=FakeLLMClient(embed_dim=8))
    container.search_index.set_meta(META_KB_MIGRATED, "2026-01-01T00:00:00+00:00")

    stats = migrate_legacy_indexes(container)
    assert stats["kb_skipped"] is True
    assert stats["kb_docs"] == 0


def test_empty_kb_still_sets_marker(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    container = build_container(Settings(kb_path=kb_path), llm=FakeLLMClient(embed_dim=8))
    stats = migrate_legacy_indexes(container)
    assert stats["kb_skipped"] is False
    assert container.search_index.get_meta(META_KB_MIGRATED) is not None


def test_embed_pending_blocked_during_kb_migration(tmp_path, monkeypatch):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    (kb_path / "doc.md").write_text("held body", encoding="utf-8")
    container = build_container(Settings(kb_path=kb_path), llm=FakeLLMClient(embed_dim=8))
    si = container.search_index
    _skip_conv_migration(si)

    embed_during_rebuild: list[int] = []
    real_rebuild = _reindex_kb_files

    def rebuild_with_embed_check(c):
        n = real_rebuild(c)
        embed_during_rebuild.append(si.embed_pending(32))
        return n

    monkeypatch.setattr("app.backup.reindex._reindex_kb_files", rebuild_with_embed_check)
    migrate_legacy_indexes(container)

    assert embed_during_rebuild == [0]
    assert si._lexical.get_item(KB_PARTITION, "doc.md::0")["vec_state"] == "pending"
    assert si.embed_pending(32) > 0


def test_reindex_kb_files_alone_does_not_set_marker(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    (kb_path / "a.md").write_text("hello\n", encoding="utf-8")
    container = build_container(Settings(kb_path=kb_path), llm=FakeLLMClient(embed_dim=8))

    n = _reindex_kb_files(container)
    assert n >= 1
    assert container.search_index.get_meta(META_KB_MIGRATED) is None


def test_reindex_all_sets_migration_marker(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    (kb_path / "a.md").write_text("hello\n", encoding="utf-8")
    container = build_container(Settings(kb_path=kb_path), llm=FakeLLMClient(embed_dim=8))

    result = reindex_all(container)
    assert result["ok"] is True
    assert container.search_index.get_meta(META_KB_MIGRATED) is not None
    assert container.search_index.get_meta(META_CONV_MIGRATED) is not None


def test_conv_migration_backfills_text(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    container = build_container(Settings(kb_path=kb_path), llm=FakeLLMClient(embed_dim=8))
    si = container.search_index
    si.set_meta(META_KB_MIGRATED, "done")

    store = container.conversations
    cid = store.create()
    turn = store.begin_turn(cid, "migrate me please", "c1", observation_allowed=False)
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={"text": "ok", "timeline": [], "sources": [], "status": "complete"},
    )
    si.drop_partition(CONV_PARTITION)

    stats = migrate_legacy_indexes(container)
    assert stats["conv_messages"] >= 1
    assert cid in container.conversation_index.conversation_ids()


def test_conv_migration_skips_deleted_conversation(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    container = build_container(Settings(kb_path=kb_path), llm=FakeLLMClient(embed_dim=8))
    container.search_index.set_meta(META_KB_MIGRATED, "done")

    ledger = kb_path / ".kb" / "migrations" / "conversation-deletions.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text('{"conversation_id": "deleted-cid"}\n', encoding="utf-8")

    migrate_legacy_indexes(container)
    assert "deleted-cid" not in container.conversation_index.conversation_ids()


def test_conv_migration_marker_skips_second_run(tmp_path):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    container = build_container(Settings(kb_path=kb_path), llm=FakeLLMClient(embed_dim=8))
    container.search_index.set_meta(META_KB_MIGRATED, "done")
    container.search_index.set_meta(META_CONV_MIGRATED, "2026-01-01T00:00:00+00:00")
    stats = migrate_legacy_indexes(container)
    assert stats["conv_skipped"] is True


def test_kb_failure_does_not_block_conv_migration(tmp_path, monkeypatch):
    kb_path = tmp_path / "knowledge"
    kb_path.mkdir()
    container = build_container(Settings(kb_path=kb_path), llm=FakeLLMClient(embed_dim=8))
    cid = container.conversations.create()
    container.conversations.begin_turn(cid, "hi", "c1", observation_allowed=False)

    monkeypatch.setattr(legacy_migration, "_migrate_kb", lambda *a, **k: None)
    migrate_legacy_indexes(container)
    assert container.search_index.get_meta(META_KB_MIGRATED) is None
    assert container.search_index.get_meta(META_CONV_MIGRATED) is not None
