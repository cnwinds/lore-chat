"""会话消息在分区检索底座上的索引。"""

from __future__ import annotations

from app.index.message_chunk import MessageChunk
from app.index.partitioned import IndexItem, SearchIndex, SyncStats

CONV_FAMILY = "conv"
CONV_PARTITION = "conv:main"
OFFSET_VERSION = "unicode-codepoint-v1"


def _group_name(conversation_id: str, message_id: str) -> str:
    _validate_ids(conversation_id, message_id)
    return f"{conversation_id}/{message_id}"


def _validate_ids(conversation_id: str, message_id: str) -> None:
    if "/" in conversation_id or "/" in message_id:
        raise ValueError("conversation_id and message_id must not contain '/'")


class ConversationIndex:
    def __init__(self, search_index: SearchIndex) -> None:
        self.search_index = search_index

    @staticmethod
    def chunk_id(conversation_id: str, message_id: str, chunk_index: int) -> str:
        return f"conv:{conversation_id}:msg:{message_id}:chunk:{chunk_index}"

    def upsert_message_chunks(
        self,
        *,
        conversation_id: str,
        message_id: str,
        role: str,
        ts: str,
        conversation_title: str,
        chunks: list[MessageChunk],
    ) -> SyncStats:
        if not chunks:
            self.delete_message(conversation_id, message_id)
            return SyncStats()
        group = _group_name(conversation_id, message_id)
        items = [
            IndexItem(
                item_id=self.chunk_id(conversation_id, message_id, c.index),
                text=c.text,
                meta={
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "role": role,
                    "ts": ts,
                    "start_char": c.start_char,
                    "end_char": c.end_char,
                    "chunk_index": c.index,
                    "conversation_title": conversation_title or "",
                    "offset_version": OFFSET_VERSION,
                },
            )
            for c in chunks
        ]
        return self.search_index.sync_group(CONV_PARTITION, group, items)

    def delete_message(self, conversation_id: str, message_id: str) -> None:
        group = _group_name(conversation_id, message_id)
        self.search_index.drop_group(CONV_PARTITION, group)

    def delete_conversation(self, conversation_id: str) -> None:
        if "/" in conversation_id:
            raise ValueError("conversation_id must not contain '/'")
        prefix = f"{conversation_id}/"
        self.search_index.drop_groups(CONV_PARTITION, prefix=prefix)

    def covered_ranges(
        self, conversation_id: str, message_id: str
    ) -> list[tuple[int, int]]:
        group = _group_name(conversation_id, message_id)
        items = self.search_index.group_items(CONV_PARTITION, group)
        ranges = [(int(it.meta["start_char"]), int(it.meta["end_char"])) for it in items]
        ranges.sort(key=lambda r: r[0])
        return ranges

    def conversation_ids(self) -> set[str]:
        out: set[str] = set()
        for group in self.search_index.groups(CONV_PARTITION):
            if "/" not in group:
                continue
            out.add(group.split("/", 1)[0])
        return out
