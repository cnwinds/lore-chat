from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field

from app.engine.provenance import conversation_ids_from_meta, group_provenance, merge_adjacent_conversation_hits
from app.engine.rrf import reciprocal_rank_fusion
from app.index.conversation_fts import ConversationFTS
from app.index.conversation_vector import ConversationVector
from app.index.revision import IndexRevision
from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.index.types import Hit
from app.logging_config import get_logger
from app.models.llm import LLMClient

_ATTACH_MARKER = "/attachments/"

# 向量余弦相似度下限；低于此视为无关（小库中否则会把全部文档都当最近邻返回）
MIN_VECTOR_SCORE = 0.45


@dataclass
class SearchPage:
    hits: list[Hit]
    has_more: bool
    next_cursor: str | None
    index_revision: int
    cursor_expired: bool = False
    provenance_groups: list[dict] = field(default_factory=list)


@dataclass
class Answer:
    text: str
    sources: list[str]
    attachments: list[str]


def _make_cursor(query: str, filters: dict, rev: int, offset: int) -> str:
    payload = {"q": query, "f": filters, "rev": rev, "off": offset}
    raw = json.dumps(payload, sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _parse_cursor(cursor: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(cursor.encode()))


class Retriever:
    def __init__(
        self,
        vector: VectorIndex,
        fulltext: FullTextIndex,
        llm: LLMClient,
        *,
        excluded_prefixes: tuple[str, ...] = (),
        min_score: float = MIN_VECTOR_SCORE,
        conversation_fts: ConversationFTS | None = None,
        conversation_vector: ConversationVector | None = None,
        index_revision: IndexRevision | None = None,
        rrf_k: int = 60,
        lane_candidate_k: int = 20,
        repo=None,
    ):
        self.vector = vector
        self.fulltext = fulltext
        self.llm = llm
        self.excluded_prefixes = tuple(excluded_prefixes)
        self.min_score = min_score
        self.conversation_fts = conversation_fts
        self.conversation_vector = conversation_vector
        self.index_revision = index_revision
        self.rrf_k = rrf_k
        self.lane_candidate_k = lane_candidate_k
        self.repo = repo

    def _excluded(self, source: str) -> bool:
        norm = (source or "").replace("\\", "/").lstrip("/")
        return any(norm.startswith(p) for p in self.excluded_prefixes)

    @staticmethod
    def _conversation_hit(ch) -> Hit:
        return Hit(
            doc_id=ch.chunk_id,
            chunk=ch.text,
            score=ch.score,
            source=f"conv:{ch.conversation_id}",
            message_id=ch.message_id,
            start_char=ch.start_char,
            end_char=ch.end_char,
            offset_version=ch.offset_version,
        )

    @staticmethod
    def _dedup_hits(hits: list[Hit]) -> list[Hit]:
        best: dict[str, Hit] = {}
        for h in hits:
            if h.doc_id in best and best[h.doc_id].score >= h.score:
                continue
            best[h.doc_id] = h
        return list(best.values())

    def _kb_fts_lane(self, query: str, lane_k: int) -> tuple[list[str], dict[str, Hit]]:
        hits = [h for h in self.fulltext.query(query, k=lane_k) if not self._excluded(h.source)]
        hits = self._dedup_hits(hits)
        hits.sort(key=lambda h: h.score, reverse=True)
        hit_map = {h.doc_id: h for h in hits}
        return [h.doc_id for h in hits], hit_map

    def _kb_vector_lane(self, query: str, lane_k: int) -> tuple[list[str], dict[str, Hit]]:
        try:
            q_emb = self.llm.embed([query])[0]
            hits = [
                h for h in self.vector.query(q_emb, k=lane_k) if h.score >= self.min_score
            ]
            hits = [h for h in hits if not self._excluded(h.source)]
            hits = self._dedup_hits(hits)
            hits.sort(key=lambda h: h.score, reverse=True)
        except Exception:
            get_logger("retriever").warning("知识库向量检索失败", exc_info=True)
            return [], {}
        hit_map = {h.doc_id: h for h in hits}
        return [h.doc_id for h in hits], hit_map

    def _conv_fts_lane(
        self, query: str, lane_k: int, *, conversation_id: str | None
    ) -> tuple[list[str], dict[str, Hit]]:
        if self.conversation_fts is None:
            return [], {}
        try:
            raw = self.conversation_fts.query(
                query, k=lane_k, conversation_id=conversation_id
            )
            hits = [self._conversation_hit(ch) for ch in raw]
        except Exception:
            get_logger("retriever").warning("会话 FTS 检索失败", exc_info=True)
            return [], {}
        hit_map = {h.doc_id: h for h in hits}
        return [h.doc_id for h in hits], hit_map

    def _conv_vector_lane(
        self, query: str, lane_k: int, *, conversation_id: str | None
    ) -> tuple[list[str], dict[str, Hit]]:
        if self.conversation_vector is None:
            return [], {}
        try:
            q_emb = self.llm.embed([query])[0]
            raw = self.conversation_vector.query(
                q_emb, k=lane_k, conversation_id=conversation_id
            )
            hits = [self._conversation_hit(ch) for ch in raw]
            hits = [h for h in hits if h.score >= self.min_score]
        except Exception:
            get_logger("retriever").warning("会话向量检索失败", exc_info=True)
            return [], {}
        hit_map = {h.doc_id: h for h in hits}
        return [h.doc_id for h in hits], hit_map

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        scope: str = "all",
        conversation_id: str | None = None,
        cursor: str | None = None,
    ) -> SearchPage:
        rev = self.index_revision.get() if self.index_revision else 0
        offset = 0
        filters = {"scope": scope, "conversation_id": conversation_id}

        if cursor:
            try:
                parsed = _parse_cursor(cursor)
                if int(parsed.get("rev", -1)) != rev:
                    return SearchPage(
                        hits=[],
                        has_more=False,
                        next_cursor=None,
                        index_revision=rev,
                        cursor_expired=True,
                    )
                query = parsed.get("q", query)
                filters = parsed.get("f", filters)
                scope = filters.get("scope", scope)
                conversation_id = filters.get("conversation_id", conversation_id)
                offset = int(parsed.get("off", 0))
            except (json.JSONDecodeError, ValueError, TypeError):
                return SearchPage(
                    hits=[],
                    has_more=False,
                    next_cursor=None,
                    index_revision=rev,
                    cursor_expired=True,
                )

        lane_k = max(self.lane_candidate_k, k * 4)
        lanes: list[list[str]] = []
        hit_map: dict[str, Hit] = {}

        use_kb = scope in ("all", "knowledge")
        use_conv = scope in ("all", "conversations")

        if use_kb:
            ids, m = self._kb_fts_lane(query, lane_k)
            if ids:
                lanes.append(ids)
                hit_map.update(m)
            ids, m = self._kb_vector_lane(query, lane_k)
            if ids:
                lanes.append(ids)
                hit_map.update(m)

        if use_conv:
            ids, m = self._conv_fts_lane(query, lane_k, conversation_id=conversation_id)
            if ids:
                lanes.append(ids)
                hit_map.update(m)
            ids, m = self._conv_vector_lane(query, lane_k, conversation_id=conversation_id)
            if ids:
                lanes.append(ids)
                hit_map.update(m)

        fused = reciprocal_rank_fusion(lanes, k=self.rrf_k)
        page_ids = [doc_id for doc_id, _ in fused[offset : offset + k]]
        page_hits = [hit_map[doc_id] for doc_id in page_ids if doc_id in hit_map]
        page_hits = merge_adjacent_conversation_hits(page_hits)

        doc_conversation_ids: dict[str, list[str]] = {}
        if self.repo:
            for h in page_hits:
                if h.source.startswith("conv:"):
                    continue
                if h.source in doc_conversation_ids:
                    continue
                try:
                    doc = self.repo.read_doc(h.source)
                    ids = conversation_ids_from_meta(doc.meta)
                    if ids:
                        doc_conversation_ids[h.source] = ids
                except FileNotFoundError:
                    pass
        provenance_groups = group_provenance(page_hits, doc_conversation_ids=doc_conversation_ids)

        next_offset = offset + k
        has_more = next_offset < len(fused)
        next_cursor = (
            _make_cursor(query, filters, rev, next_offset) if has_more else None
        )

        return SearchPage(
            hits=page_hits,
            has_more=has_more,
            next_cursor=next_cursor,
            index_revision=rev,
            provenance_groups=provenance_groups,
        )

    def answer(self, query: str, k: int = 5) -> Answer:
        page = self.search(query, k=k)
        hits = page.hits
        if not hits:
            return Answer(text="我没有找到相关内容。", sources=[], attachments=[])
        context = "\n\n".join(f"[来源: {h.source}]\n{h.chunk}" for h in hits)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是知识库助手。只依据提供的资料回答；资料中没有就明确说没有，不要编造。"
                    "回答简洁，并在末尾不必重复来源（系统会单独展示）。"
                ),
            },
            {"role": "user", "content": f"资料：\n{context}\n\n问题：{query}"},
        ]
        text = self.llm.chat(messages, big=True)
        sources = list(dict.fromkeys(h.source for h in hits))
        attachments = [s for s in sources if _ATTACH_MARKER in s]
        return Answer(text=text, sources=sources, attachments=attachments)
