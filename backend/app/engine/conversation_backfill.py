"""历史 FTS / 向量回填：为 SQLite `ConversationStore` 中已保留的消息补写索引。

用于覆盖两类场景：迁移自旧 JSON 分片但 outbox 尚未被 worker 消费的消息，以及
worker 失败/未运行期间产生的缺口。幂等：已完整覆盖的消息不会被重复写入；
已判定删除（deletion ledger）的会话会被跳过。

可执行：
  python -m app.engine.conversation_backfill          # FTS 回填
  python -m app.engine.conversation_backfill --vectors  # 向量回填（支持 checkpoint）
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.engine.conversations import ConversationStore
from app.engine.secrets import mask_secrets
from app.index.conversation_fts import ConversationFTS
from app.index.conversation_vector import ConversationVector
from app.index.message_chunk import MessageChunk, chunk_message, coverage_ok
from app.models.llm import LLMClient


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


def _is_message_covered(fts: ConversationFTS, cid: str, message_id: str, text: str) -> bool:
    ranges = fts.covered_ranges(cid, message_id)
    if not ranges:
        return False
    chunks = [MessageChunk(i, start, end, "") for i, (start, end) in enumerate(ranges)]
    return coverage_ok(text, chunks)


def _load_checkpoint(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {"last_message_id": None, "indexed": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"last_message_id": None, "indexed": 0}
    return {
        "last_message_id": data.get("last_message_id"),
        "indexed": int(data.get("indexed") or 0),
    }


def _save_checkpoint(path: Path | None, last_message_id: str, indexed: int) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"last_message_id": last_message_id, "indexed": indexed}, ensure_ascii=False),
        encoding="utf-8",
    )


def _iter_messages(store: ConversationStore, deleted_cids: set[str]):
    for summary in store.list_all():
        cid = summary["id"]
        if cid in deleted_cids:
            yield "deleted", cid, None, None
            continue
        conv = store.get(cid)
        for msg in conv.get("messages", []):
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue
            yield "message", cid, conv, msg


def _is_message_vector_covered(
    vector: ConversationVector,
    cid: str,
    message_id: str,
    masked_text: str,
    *,
    chunk_chars: int,
    overlap: int,
) -> bool:
    chunks = chunk_message(masked_text, size=chunk_chars, overlap=overlap)
    if not chunks:
        return True
    return vector.count_for_message(cid, message_id) == len(chunks)


def backfill_conversation_vectors(
    store: ConversationStore,
    vector: ConversationVector,
    llm: LLMClient,
    deletion_ledger_path: str | Path | None = None,
    *,
    checkpoint_path: Path | None = None,
    chunk_chars: int = 1000,
    overlap: int = 150,
    batch_size: int = 20,
) -> dict:
    """跳过 ledger 已删 cid；按 message id 序处理；checkpoint 记录 last_message_id。"""
    deleted_cids = _load_deleted_cids(deletion_ledger_path)
    checkpoint = _load_checkpoint(checkpoint_path)
    resume_after = checkpoint.get("last_message_id")
    skipping = resume_after is not None

    scanned = 0
    indexed = checkpoint.get("indexed", 0)
    skipped_deleted = 0
    skipped_empty = 0
    newly_indexed = 0

    pending: list[tuple[str, str, dict, dict, list]] = []

    def flush_batch() -> None:
        nonlocal indexed, newly_indexed
        if not pending:
            return
        flat_texts = [c.text for _cid, _mid, _conv, _msg, chunks in pending for c in chunks]
        if not flat_texts:
            pending.clear()
            return
        embs = llm.embed(flat_texts)
        emb_i = 0
        for cid, message_id, conv, msg, chunks in pending:
            msg_embs = embs[emb_i : emb_i + len(chunks)]
            emb_i += len(chunks)
            vector.upsert_message_chunks(
                conversation_id=cid,
                message_id=message_id,
                role=msg.get("role", ""),
                ts=msg.get("ts", ""),
                conversation_title=conv.get("title", ""),
                chunks=chunks,
                embeddings=msg_embs,
            )
            indexed += 1
            newly_indexed += 1
            if checkpoint_path is not None:
                _save_checkpoint(checkpoint_path, message_id, indexed)
        pending.clear()

    message_rows: list[tuple[str, str, dict, dict]] = []
    for kind, cid, conv, msg in _iter_messages(store, deleted_cids):
        if kind == "deleted":
            skipped_deleted += 1
            continue
        assert conv is not None and msg is not None
        message_rows.append((msg["id"], cid, conv, msg))
    message_rows.sort(key=lambda row: row[0])

    for message_id, cid, conv, msg in message_rows:
        if skipping:
            if message_id == resume_after:
                skipping = False
            continue

        text = msg.get("text") or ""
        if not text.strip():
            skipped_empty += 1
            continue

        scanned += 1
        masked_text, _ = mask_secrets(text)
        if _is_message_vector_covered(
            vector, cid, message_id, masked_text, chunk_chars=chunk_chars, overlap=overlap
        ):
            continue

        chunks = chunk_message(masked_text, size=chunk_chars, overlap=overlap)
        if not chunks or not coverage_ok(masked_text, chunks):
            continue

        pending.append((cid, message_id, conv, msg, chunks))
        if len(pending) >= batch_size:
            flush_batch()

    flush_batch()

    return {
        "scanned": scanned,
        "indexed": newly_indexed,
        "total_indexed": indexed,
        "skipped_deleted": skipped_deleted,
        "skipped_empty": skipped_empty,
        "checkpoint": checkpoint_path.name if checkpoint_path else None,
    }


def backfill_conversation_fts(
    store: ConversationStore,
    fts: ConversationFTS,
    deletion_ledger_path: str | Path | None = None,
    *,
    chunk_chars: int = 1000,
    overlap: int = 150,
) -> dict:
    """扫描全部保留会话的消息，为缺失/未完整覆盖的消息同步补写消息级 FTS。

    与 `DerivationWorker` 复用同一套脱敏 + 分块逻辑（mask_secrets → chunk_message），
    但直接同步 upsert，不经过 outbox，用于一次性回填历史数据或修复 worker 遗留缺口。
    """
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
    conversation_fts: ConversationFTS,
    conversation_vector: ConversationVector | None = None,
    indexer=None,
    index_revision=None,
) -> dict:
    """按 deletion ledger 清理已删会话在 FTS/向量/遗留索引中的残留 chunk。"""
    deleted = _load_deleted_cids(ledger_path)
    if not deleted:
        return {"deleted_cids": 0, "purged": 0}
    for cid in deleted:
        conversation_fts.delete_conversation(cid)
        if conversation_vector is not None:
            try:
                conversation_vector.delete_conversation(cid)
            except Exception:
                pass
        if indexer is not None:
            indexer.remove_conversation(cid)
    if index_revision is not None:
        index_revision.bump()
    return {"deleted_cids": len(deleted), "purged": len(deleted)}


def main() -> None:
    from app.config import get_settings
    from app.index.revision import IndexRevision
    from app.models.llm import OpenAILLMClient

    parser = argparse.ArgumentParser(description="回填会话消息级 FTS 或向量索引")
    parser.add_argument(
        "--vectors",
        action="store_true",
        help="回填 ConversationVector（默认仅 FTS）",
    )
    parser.add_argument(
        "--purge-deleted",
        action="store_true",
        help="按 deletion ledger 清理已删会话的 FTS/向量/遗留索引残留",
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help="向量回填 checkpoint 文件路径（默认 index/vector-backfill.checkpoint.json）",
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

    if args.purge_deleted:
        from app.index.fulltext import FullTextIndex
        from app.index.indexer import Indexer
        from app.index.vector import VectorIndex

        fts = ConversationFTS(index_dir / "conversation_fts.db")
        vector = ConversationVector(index_dir / "vec")
        llm = OpenAILLMClient(settings)
        indexer = Indexer(VectorIndex(index_dir / "vec"), FullTextIndex(index_dir / "fts.db"), llm)
        stats = purge_deleted_conversation_indexes(
            ledger_path=ledger_path,
            conversation_fts=fts,
            conversation_vector=vector,
            indexer=indexer,
            index_revision=index_revision,
        )
        print(json.dumps(stats, ensure_ascii=False))
        return

    if args.vectors:
        checkpoint_path = (
            Path(args.checkpoint)
            if args.checkpoint
            else index_dir / "vector-backfill.checkpoint.json"
        )
        vector = ConversationVector(index_dir / "vec")
        llm = OpenAILLMClient(settings)
        stats = backfill_conversation_vectors(
            store,
            vector,
            llm,
            ledger_path,
            checkpoint_path=checkpoint_path,
            chunk_chars=chunk_chars,
            overlap=overlap,
        )
    else:
        fts = ConversationFTS(index_dir / "conversation_fts.db")
        stats = backfill_conversation_fts(
            store,
            fts,
            ledger_path,
            chunk_chars=chunk_chars,
            overlap=overlap,
        )
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
