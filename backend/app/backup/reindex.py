from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from app.engine.conversation_backfill import backfill_conversation_fts
from app.engine.knowledge_writer import is_markdown_path
from app.index.extract import extract_text
from app.index.kb_index import KB_PARTITION, normalize_kb_path
from app.logging_config import get_logger

if TYPE_CHECKING:
    from app.deps import Container

_log = get_logger("backup.reindex")


def _reindex_kb_files(container: Container) -> int:
    """重建文档索引：Markdown 走 frontmatter；其它文件尽量抽取文本，跳过纯二进制。"""
    docs_indexed = 0
    rebuilt_groups: set[str] = set()
    for rel_path in container.repo.list_tree():
        if is_markdown_path(rel_path):
            try:
                doc = container.repo.read_doc(rel_path)
            except (UnicodeDecodeError, OSError, ValueError) as exc:
                _log.warning("skip markdown reindex path=%s err=%s", rel_path, exc)
                continue
            container.knowledge_writer.reindex_markdown_body(rel_path, doc.body)
            rebuilt_groups.add(normalize_kb_path(rel_path))
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
            rebuilt_groups.add(normalize_kb_path(rel_path))
            docs_indexed += 1
    search_index = container.search_index
    for group in search_index.groups(KB_PARTITION):
        if group not in rebuilt_groups:
            search_index.drop_group(KB_PARTITION, group)
    return docs_indexed


def reindex_all(container: Container) -> dict:
    """Rebuild document / conversation / card indexes on partitioned base."""
    from app.index.legacy_migration import (
        write_conv_migration_marker,
        write_kb_migration_marker,
    )

    docs_indexed = _reindex_kb_files(container)
    try:
        write_kb_migration_marker(container.search_index)
    except Exception as exc:
        _log.warning("写入 legacy_kb_migrated_at 失败: %s", exc)

    settings = container.settings
    ledger_path = settings.kb_path / ".kb" / "migrations" / "conversation-deletions.jsonl"
    chunk_chars = settings.conversation_chunk_chars
    overlap = settings.conversation_chunk_overlap_chars

    fts_stats = backfill_conversation_fts(
        container.conversations,
        container.conversation_index,
        ledger_path,
        chunk_chars=chunk_chars,
        overlap=overlap,
    )

    live_cids = {s["id"] for s in container.conversations.list_all()}
    for cid in container.conversation_index.conversation_ids():
        if cid not in live_cids:
            container.conversation_index.delete_conversation(cid)

    try:
        write_conv_migration_marker(container.search_index)
    except Exception as exc:
        _log.warning("写入 legacy_conv_migrated_at 失败: %s", exc)

    cards_indexed = 0
    card_index = getattr(container, "card_index", None)
    if card_index is not None:
        try:
            rebuild_stats = card_index.rebuild()
            cards_indexed = int(rebuild_stats.get("cards_indexed") or 0)
        except Exception as exc:
            _log.warning("card index rebuild failed: %s", exc, exc_info=True)

    owner_facts_indexed = 0
    owner_memory_index = getattr(container, "owner_memory_index", None)
    if owner_memory_index is not None:
        try:
            owner_stats = owner_memory_index.rebuild()
            owner_facts_indexed = int(owner_stats.get("facts_indexed") or 0)
        except Exception as exc:
            _log.warning("owner index rebuild failed: %s", exc, exc_info=True)

    container.index_revision.bump()

    return {
        "ok": True,
        "docs_indexed": docs_indexed,
        "conversations_fts": fts_stats.get("indexed", 0),
        "conversations_vector": 0,
        "cards_indexed": cards_indexed,
        "owner_facts_indexed": owner_facts_indexed,
    }
