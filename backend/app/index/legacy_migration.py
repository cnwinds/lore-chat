from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.engine.conversation_backfill import backfill_conversation_fts
from app.index.conversation_index import CONV_FAMILY
from app.index.kb_index import KB_FAMILY
from app.index.partitioned import SearchIndex
from app.logging_config import get_logger

if TYPE_CHECKING:
    from app.deps import Container

_log = get_logger("index.legacy_migration")

META_KB_MIGRATED = "legacy_kb_migrated_at"
META_CONV_MIGRATED = "legacy_conv_migrated_at"


def write_kb_migration_marker(search_index: SearchIndex) -> None:
    search_index.set_meta(META_KB_MIGRATED, datetime.now(timezone.utc).isoformat())


def write_conv_migration_marker(search_index: SearchIndex) -> None:
    search_index.set_meta(META_CONV_MIGRATED, datetime.now(timezone.utc).isoformat())


def _migrate_kb(container: Container) -> dict | None:
    try:
        from app.backup.reindex import _reindex_kb_files

        kb_docs = _reindex_kb_files(container)
    except Exception:
        _log.warning("迁移：重建文档库全文失败", exc_info=True)
        return None

    return {"kb_docs": kb_docs}


def _migrate_conversations(container: Container) -> dict | None:
    settings = container.settings
    ledger_path = settings.kb_path / ".kb" / "migrations" / "conversation-deletions.jsonl"
    try:
        fts_stats = backfill_conversation_fts(
            container.conversations,
            container.conversation_index,
            ledger_path,
            chunk_chars=settings.conversation_chunk_chars,
            overlap=settings.conversation_chunk_overlap_chars,
        )
    except Exception:
        _log.warning("迁移：会话全文回填失败", exc_info=True)
        return None

    return {"conv_messages": int(fts_stats.get("indexed") or 0)}


def migrate_legacy_indexes(container: Container) -> dict:
    """旧栈全文迁入分区底座（文档库 + 会话，各自独立标记）；向量由后台重嵌。"""
    stats: dict = {
        "kb_docs": 0,
        "kb_skipped": False,
        "conv_messages": 0,
        "conv_skipped": False,
    }
    search_index = container.search_index
    bumped = False

    try:
        kb_done = bool(search_index.get_meta(META_KB_MIGRATED))
    except Exception:
        _log.warning("读取文档库迁移标记失败", exc_info=True)
        kb_done = True

    if kb_done:
        stats["kb_skipped"] = True
    else:
        try:
            with search_index.embedding_held(KB_FAMILY):
                kb_stats = _migrate_kb(container)
            if kb_stats is not None:
                try:
                    write_kb_migration_marker(search_index)
                    stats["kb_docs"] = kb_stats["kb_docs"]
                    bumped = True
                except Exception:
                    _log.warning("迁移：写入文档库完成标记失败", exc_info=True)
        except Exception:
            _log.warning("迁移：文档库阶段失败", exc_info=True)

    try:
        conv_done = bool(search_index.get_meta(META_CONV_MIGRATED))
    except Exception:
        _log.warning("读取会话迁移标记失败", exc_info=True)
        conv_done = True

    if conv_done:
        stats["conv_skipped"] = True
    else:
        try:
            with search_index.embedding_held(CONV_FAMILY):
                conv_stats = _migrate_conversations(container)
            if conv_stats is not None:
                try:
                    write_conv_migration_marker(search_index)
                    stats["conv_messages"] = conv_stats["conv_messages"]
                    bumped = True
                except Exception:
                    _log.warning("迁移：写入会话完成标记失败", exc_info=True)
        except Exception:
            _log.warning("迁移：会话阶段失败", exc_info=True)

    if bumped:
        try:
            container.index_revision.bump()
        except Exception:
            _log.warning("迁移：bump index_revision 失败", exc_info=True)

    return stats
