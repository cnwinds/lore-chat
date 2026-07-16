from __future__ import annotations

from typing import TYPE_CHECKING

from app.engine.conversation_backfill import (
    backfill_conversation_fts,
    backfill_conversation_vectors,
)

if TYPE_CHECKING:
    from app.deps import Container


def reindex_all(container: Container) -> dict:
    """Rebuild document FTS/vector indexes and backfill conversation indexes."""
    docs_indexed = 0
    for rel_path in container.repo.list_tree():
        doc = container.repo.read_doc(rel_path)
        container.indexer.reindex_doc(rel_path, doc.body)
        docs_indexed += 1

    settings = container.settings
    ledger_path = settings.kb_path / ".kb" / "migrations" / "conversation-deletions.jsonl"
    chunk_chars = settings.conversation_chunk_chars
    overlap = settings.conversation_chunk_overlap_chars

    fts_stats = backfill_conversation_fts(
        container.conversations,
        container.conversation_fts,
        ledger_path,
        chunk_chars=chunk_chars,
        overlap=overlap,
    )
    vector_stats = backfill_conversation_vectors(
        container.conversations,
        container.conversation_vector,
        container.llm,
        ledger_path,
        checkpoint_path=None,
        chunk_chars=chunk_chars,
        overlap=overlap,
    )

    container.index_revision.bump()

    return {
        "ok": True,
        "docs_indexed": docs_indexed,
        "conversations_fts": fts_stats.get("indexed", 0),
        "conversations_vector": vector_stats.get("indexed", 0),
    }
