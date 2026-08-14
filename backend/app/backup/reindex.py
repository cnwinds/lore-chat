from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from app.engine.conversation_backfill import (
    backfill_conversation_fts,
    backfill_conversation_vectors,
)
from app.engine.knowledge_writer import is_markdown_path
from app.index.extract import extract_text
from app.logging_config import get_logger

if TYPE_CHECKING:
    from app.deps import Container

_log = get_logger("backup.reindex")


def _reindex_kb_files(container: Container) -> int:
    """重建文档索引：Markdown 走 frontmatter；其它文件尽量抽取文本，跳过纯二进制。"""
    docs_indexed = 0
    for rel_path in container.repo.list_tree():
        if is_markdown_path(rel_path):
            try:
                doc = container.repo.read_doc(rel_path)
            except (UnicodeDecodeError, OSError, ValueError) as exc:
                _log.warning("skip markdown reindex path=%s err=%s", rel_path, exc)
                continue
            container.knowledge_writer.reindex_markdown_body(rel_path, doc.body)
            docs_indexed += 1
            continue

        # 图片等：extract_text 返回空则跳过，避免 read_doc 的 UTF-8 崩溃
        abs_path = container.repo.abs_path(rel_path)
        try:
            extracted = extract_text(abs_path)
        except OSError as exc:
            _log.warning("skip extract path=%s err=%s", rel_path, exc)
            continue
        if not extracted.strip():
            _log.debug(
                "skip non-text asset path=%s suffix=%s",
                rel_path,
                PurePosixPath(rel_path).suffix,
            )
            continue
        if container.knowledge_writer.index_extracted_text(rel_path, extracted):
            docs_indexed += 1
    return docs_indexed


def reindex_all(container: Container) -> dict:
    """Rebuild document FTS/vector indexes and backfill conversation indexes."""
    docs_indexed = _reindex_kb_files(container)

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
    try:
        vector_stats = backfill_conversation_vectors(
            container.conversations,
            container.conversation_vector,
            container.llm,
            ledger_path,
            checkpoint_path=None,
            chunk_chars=chunk_chars,
            overlap=overlap,
        )
    except Exception as exc:
        # 嵌入 API 不可达时仍保留 FTS；避免整次「重建索引」失败
        _log.warning("conversation vector backfill failed: %s", exc, exc_info=True)
        vector_stats = {"indexed": 0, "error": str(exc)}

    container.index_revision.bump()

    return {
        "ok": True,
        "docs_indexed": docs_indexed,
        "conversations_fts": fts_stats.get("indexed", 0),
        "conversations_vector": vector_stats.get("indexed", 0),
    }
