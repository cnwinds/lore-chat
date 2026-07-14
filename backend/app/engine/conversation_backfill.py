"""历史 FTS 回填：为 SQLite `ConversationStore` 中已保留的消息补写 `conversation_chunks_v2`。

用于覆盖两类场景：迁移自旧 JSON 分片但 outbox 尚未被 worker 消费的消息，以及
worker 失败/未运行期间产生的缺口。幂等：已完整覆盖（按 codepoint 区间）的消息
不会被重复写入；已判定删除（deletion ledger）的会话会被跳过。

可执行：`python -m app.engine.conversation_backfill`
"""

from __future__ import annotations

import json
from pathlib import Path

from app.engine.conversations import ConversationStore
from app.engine.secrets import mask_secrets
from app.index.conversation_fts import ConversationFTS
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


def _is_message_covered(fts: ConversationFTS, cid: str, message_id: str, text: str) -> bool:
    ranges = fts.covered_ranges(cid, message_id)
    if not ranges:
        return False
    chunks = [MessageChunk(i, start, end, "") for i, (start, end) in enumerate(ranges)]
    return coverage_ok(text, chunks)


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


def main() -> None:
    from app.config import get_settings

    settings = get_settings()
    conversations_dir = settings.kb_path / ".kb" / "conversations"
    index_dir = settings.kb_path / ".kb" / "index"
    ledger_path = conversations_dir.parent / "migrations" / "conversation-deletions.jsonl"

    store = ConversationStore(conversations_dir)
    fts = ConversationFTS(index_dir / "conversation_fts.db")
    stats = backfill_conversation_fts(
        store,
        fts,
        ledger_path,
        chunk_chars=settings.conversation_chunk_chars,
        overlap=settings.conversation_chunk_overlap_chars,
    )
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
