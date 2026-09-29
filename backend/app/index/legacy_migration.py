from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.engine.conversation_backfill import backfill_conversation_fts
from app.index.chroma_client import make_persistent_client
from app.index.conversation_index import CONV_FAMILY, CONV_PARTITION
from app.index.kb_index import KB_FAMILY, KB_PARTITION
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


def _adopt_legacy_collection(
    search_index: SearchIndex,
    vec_dir,
    collection_name: str,
    partition: str,
    *,
    model: str,
    page_size: int,
) -> int | None:
    """沿用旧 Chroma 集合向量。返回沿用条数；集合不存在返回 0；客户端/分页致命失败返回 None。"""
    try:
        client = make_persistent_client(str(vec_dir))
    except Exception:
        _log.warning("迁移：打开旧向量库失败", exc_info=True)
        return None

    try:
        col = client.get_collection(collection_name)
    except Exception:
        return 0

    adopted = 0
    off = 0
    while True:
        try:
            page = col.get(
                include=["embeddings", "documents"],
                limit=page_size,
                offset=off,
            )
        except Exception:
            _log.warning(
                "迁移：读取旧集合 %s 分页失败 offset=%s",
                collection_name,
                off,
                exc_info=True,
            )
            return None

        ids = page.get("ids") or []
        if not ids:
            break

        docs = page.get("documents")
        if docs is None:
            docs = []
        embs = page.get("embeddings")
        if embs is None:
            embs = []

        rows: list[tuple[str, str, list[float]]] = []
        for i, item_id in enumerate(ids):
            doc = docs[i] if i < len(docs) else ""
            emb = embs[i] if i < len(embs) else None
            if not doc or emb is None:
                continue
            vec = [float(x) for x in emb]
            rows.append((item_id, doc, vec))

        if rows:
            try:
                adopted += search_index.adopt_vectors(partition, rows, model=model)
            except Exception:
                _log.warning(
                    "迁移：沿用旧向量批次失败 collection=%s offset=%s",
                    collection_name,
                    off,
                    exc_info=True,
                )

        if len(ids) < page_size:
            break
        off += page_size

    return adopted


def _migrate_kb(container: Container, search_index: SearchIndex, page_size: int) -> dict | None:
    try:
        from app.backup.reindex import _reindex_kb_files

        kb_docs = _reindex_kb_files(container)
    except Exception:
        _log.warning("迁移：重建文档库全文失败", exc_info=True)
        return None

    kb_adopted = 0
    model: str | None = None
    try:
        model = search_index.probe_model()
    except Exception:
        _log.warning("迁移：嵌入模型探测失败", exc_info=True)

    if model is not None:
        vec_dir = container.settings.kb_path / ".kb" / "index" / "vec"
        adopted = _adopt_legacy_collection(
            search_index,
            vec_dir,
            "kbs",
            KB_PARTITION,
            model=model,
            page_size=page_size,
        )
        if adopted is None:
            return None
        kb_adopted = adopted

    return {"kb_docs": kb_docs, "kb_adopted": kb_adopted}


def _migrate_conversations(
    container: Container, search_index: SearchIndex, page_size: int
) -> dict | None:
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

    conv_adopted = 0
    model: str | None = None
    try:
        model = search_index.probe_model()
    except Exception:
        _log.warning("迁移：会话嵌入模型探测失败", exc_info=True)

    if model is not None:
        vec_dir = settings.kb_path / ".kb" / "index" / "vec"
        adopted = _adopt_legacy_collection(
            search_index,
            vec_dir,
            "conversation_chunks_v2",
            CONV_PARTITION,
            model=model,
            page_size=page_size,
        )
        if adopted is None:
            return None
        conv_adopted = adopted

    return {
        "conv_messages": int(fts_stats.get("indexed") or 0),
        "conv_adopted": conv_adopted,
    }


def migrate_legacy_indexes(container: Container, *, page_size: int = 256) -> dict:
    """旧 Chroma 向量迁入分区底座（文档库 + 会话，各自独立标记）。"""
    stats: dict = {
        "kb_docs": 0,
        "kb_adopted": 0,
        "kb_skipped": False,
        "conv_messages": 0,
        "conv_adopted": 0,
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
                kb_stats = _migrate_kb(container, search_index, page_size)
            if kb_stats is not None:
                try:
                    write_kb_migration_marker(search_index)
                    stats["kb_docs"] = kb_stats["kb_docs"]
                    stats["kb_adopted"] = kb_stats["kb_adopted"]
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
                conv_stats = _migrate_conversations(container, search_index, page_size)
            if conv_stats is not None:
                try:
                    write_conv_migration_marker(search_index)
                    stats["conv_messages"] = conv_stats["conv_messages"]
                    stats["conv_adopted"] = conv_stats["conv_adopted"]
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
