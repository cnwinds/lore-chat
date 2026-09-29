"""历史会话索引回填：为 SQLite `ConversationStore` 中已保留的消息补写分区索引。

可执行：
  python -m app.engine.conversation_backfill
  python -m app.engine.conversation_backfill --purge-deleted
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.engine.conversations import ConversationStore
from app.engine.secrets import mask_secrets
from app.index.conversation_index import ConversationIndex
from app.index.message_chunk import MessageChunk, chunk_message, coverage_ok


def _load_deleted_cids(ledger_path: str | Path | None) -> set[str]:
    if not ledger_path:
        return set()
    path = Path(ledger_path)
    if not path.exists():
        return set()
    deleted: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        cid = entry.get("conversation_id")
        if cid:
            deleted.add(cid)
    return deleted


def _is_message_covered(
    index: ConversationIndex, cid: str, message_id: str, text: str
) -> bool:
    ranges = index.covered_ranges(cid, message_id)
    if not ranges:
        return False
    chunks = [MessageChunk(i, start, end, "") for i, (start, end) in enumerate(ranges)]
    return coverage_ok(text, chunks)


def backfill_conversation_fts(
    store: ConversationStore,
    fts: ConversationIndex,
    deletion_ledger_path: str | Path | None = None,
    *,
    chunk_chars: int = 1000,
    overlap: int = 150,
) -> dict:
    """扫描全部保留会话的消息，为缺失/未完整覆盖的消息同步补写索引。"""
    deleted_cids = _load_deleted_cids(deletion_ledger_path)
    scanned = 0
    indexed = 0
    skipped_deleted = 0
    skipped_empty = 0

    for summary in store.list_all():
        cid = summary["id"]
        if cid in deleted_cids:
            skipped_deleted += 1
            continue

        conv = store.get(cid)
        for msg in conv.get("messages", []):
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue

            text = msg.get("text") or ""
            if not text.strip():
                skipped_empty += 1
                continue

            scanned += 1
            message_id = msg["id"]
            if _is_message_covered(fts, cid, message_id, text):
                continue

            masked_text, _ = mask_secrets(text)
            chunks = chunk_message(masked_text, size=chunk_chars, overlap=overlap)
            if not chunks or not coverage_ok(masked_text, chunks):
                continue

            fts.upsert_message_chunks(
                conversation_id=cid,
                message_id=message_id,
                role=role,
                ts=msg.get("ts", ""),
                conversation_title=conv.get("title", ""),
                chunks=chunks,
            )
            indexed += 1

    return {
        "scanned": scanned,
        "indexed": indexed,
        "skipped_deleted": skipped_deleted,
        "skipped_empty": skipped_empty,
    }


def purge_deleted_conversation_indexes(
    *,
    ledger_path: str | Path,
    conversation_index: ConversationIndex,
    index_revision=None,
) -> dict:
    """按 deletion ledger 清理已删会话在索引中的残留 chunk。"""
    deleted = _load_deleted_cids(ledger_path)
    if not deleted:
        return {"deleted_cids": 0, "purged": 0}
    for cid in deleted:
        conversation_index.delete_conversation(cid)
    if index_revision is not None:
        index_revision.bump()
    return {"deleted_cids": len(deleted), "purged": len(deleted)}


def main() -> None:
    from app.config import get_settings
    from app.index.conversation_index import ConversationIndex
    from app.index.partitioned import LLMEmbedder, SearchIndex
    from app.index.revision import IndexRevision
    from app.models.llm import OpenAILLMClient

    parser = argparse.ArgumentParser(description="回填会话消息级索引")
    parser.add_argument(
        "--purge-deleted",
        action="store_true",
        help="按 deletion ledger 清理已删会话的索引残留",
    )
    args = parser.parse_args()

    settings = get_settings()
    conversations_dir = settings.kb_path / ".kb" / "conversations"
    index_dir = settings.kb_path / ".kb" / "index"
    ledger_path = conversations_dir.parent / "migrations" / "conversation-deletions.jsonl"

    store = ConversationStore(conversations_dir)
    chunk_chars = settings.conversation_chunk_chars
    overlap = settings.conversation_chunk_overlap_chars
    index_revision = IndexRevision(index_dir / "revision.txt")
    llm = OpenAILLMClient(settings)
    search_index = SearchIndex(
        index_dir / "partitioned.db",
        index_dir / "vec",
        LLMEmbedder(llm),
    )
    conv_index = ConversationIndex(search_index)

    if args.purge_deleted:
        stats = purge_deleted_conversation_indexes(
            ledger_path=ledger_path,
            conversation_index=conv_index,
            index_revision=index_revision,
        )
        print(json.dumps(stats, ensure_ascii=False))
        return

    stats = backfill_conversation_fts(
        store,
        conv_index,
        ledger_path,
        chunk_chars=chunk_chars,
        overlap=overlap,
    )
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
