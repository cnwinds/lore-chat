from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field

from app.engine.provenance import (
    conversation_ids_from_meta,
    group_provenance,
    merge_adjacent_conversation_hits,
)
from app.engine.rrf import reciprocal_rank_fusion
from app.engine.search_quality import (
    HitMeta,
    assess_lane_strength,
    gate_page_hits,
    should_drop_vector_lane,
)
from app.index.conversation_fts import ConversationFTS
from app.index.conversation_vector import ConversationVector
from app.index.fulltext import FullTextIndex
from app.index.revision import IndexRevision
from app.index.search_query import compile_search_query
from app.index.types import Hit
from app.index.vector import VectorIndex
from app.logging_config import get_logger
from app.models.llm import LLMClient
from app.engine.knowledge_writer import is_markdown_path

# 向量余弦相似度下限；低于此视为无关（小库中否则会把全部文档都当最近邻返回）
MIN_VECTOR_SCORE = 0.50

DEFAULT_LANE_WEIGHTS = (0.9, 1.0, 0.5, 0.7)  # kb_fts, kb_vec, conv_fts, conv_vec


@dataclass
class SearchPage:
    hits: list[Hit]
    has_more: bool
    next_cursor: str | None
    index_revision: int
    cursor_expired: bool = False
    provenance_groups: list[dict] = field(default_factory=list)
    match_strength: str = "none"


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
        lane_weights: tuple[float, float, float, float] = DEFAULT_LANE_WEIGHTS,
        kb_first_throttle: bool = True,
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
        self.lane_weights = lane_weights
        self.kb_first_throttle = kb_first_throttle
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
            role=ch.role or None,
            ts=ch.ts or None,
            conversation_title=ch.conversation_title or None,
        )

    @staticmethod
    def _dedup_hits(hits: list[Hit]) -> list[Hit]:
        best: dict[str, Hit] = {}
        for h in hits:
            if h.doc_id in best and best[h.doc_id].score >= h.score:
                continue
            best[h.doc_id] = h
        return list(best.values())

    def _kb_fts_lane(
        self, query: str, lane_k: int
    ) -> tuple[list[str], dict[str, Hit], dict[str, HitMeta]]:
        outcome = self.fulltext.query_with_tier(query, k=lane_k)
        hits = [h for h in outcome.hits if not self._excluded(h.source)]
        hits = self._dedup_hits(hits)
        hits.sort(key=lambda h: h.score, reverse=True)
        hit_map = {h.doc_id: h for h in hits}
        meta_map = {
            h.doc_id: HitMeta(lane="kb_fts", fts_tier=outcome.tier) for h in hits
        }
        return [h.doc_id for h in hits], hit_map, meta_map

    def _kb_vector_lane(
        self, query: str, lane_k: int, *, vector_text: str
    ) -> tuple[list[str], dict[str, Hit], dict[str, HitMeta]]:
        try:
            q_emb = self.llm.embed([vector_text])[0]
            hits = [
                h for h in self.vector.query(q_emb, k=lane_k) if h.score >= self.min_score
            ]
            hits = [h for h in hits if not self._excluded(h.source)]
            hits = self._dedup_hits(hits)
            hits.sort(key=lambda h: h.score, reverse=True)
            if should_drop_vector_lane(hits):
                return [], {}, {}
        except Exception:
            get_logger("retriever").warning("知识库向量检索失败", exc_info=True)
            return [], {}, {}
        hit_map = {h.doc_id: h for h in hits}
        meta_map = {
            h.doc_id: HitMeta(lane="kb_vector", vector_score=h.score) for h in hits
        }
        return [h.doc_id for h in hits], hit_map, meta_map

    def _conv_fts_lane(
        self,
        query: str,
        lane_k: int,
        *,
        conversation_id: str | None,
        exclude_conversation_id: str | None,
    ) -> tuple[list[str], dict[str, Hit], dict[str, HitMeta]]:
        if self.conversation_fts is None:
            return [], {}, {}
        try:
            outcome = self.conversation_fts.query_with_tier(
                query,
                k=lane_k,
                conversation_id=conversation_id,
                exclude_conversation_id=exclude_conversation_id,
            )
            hits = [self._conversation_hit(ch) for ch in outcome.hits]
        except Exception:
            get_logger("retriever").warning("会话 FTS 检索失败", exc_info=True)
            return [], {}, {}
        hit_map = {h.doc_id: h for h in hits}
        meta_map = {
            h.doc_id: HitMeta(lane="conv_fts", fts_tier=outcome.tier) for h in hits
        }
        return [h.doc_id for h in hits], hit_map, meta_map

    def _conv_vector_lane(
        self,
        query: str,
        lane_k: int,
        *,
        vector_text: str,
        conversation_id: str | None,
        exclude_conversation_id: str | None,
    ) -> tuple[list[str], dict[str, Hit], dict[str, HitMeta]]:
        if self.conversation_vector is None:
            return [], {}, {}
        try:
            q_emb = self.llm.embed([vector_text])[0]
            raw = self.conversation_vector.query(
                q_emb,
                k=lane_k,
                conversation_id=conversation_id,
                exclude_conversation_id=exclude_conversation_id,
            )
            hits = [self._conversation_hit(ch) for ch in raw]
            hits = [h for h in hits if h.score >= self.min_score]
            if should_drop_vector_lane(hits):
                return [], {}, {}
        except Exception:
            get_logger("retriever").warning("会话向量检索失败", exc_info=True)
            return [], {}, {}
        hit_map = {h.doc_id: h for h in hits}
        meta_map = {
            h.doc_id: HitMeta(lane="conv_vector", vector_score=h.score) for h in hits
        }
        return [h.doc_id for h in hits], hit_map, meta_map

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        scope: str = "all",
        conversation_id: str | None = None,
        exclude_conversation_id: str | None = None,
        cursor: str | None = None,
    ) -> SearchPage:
        rev = self.index_revision.get() if self.index_revision else 0
        offset = 0
        filters = {
            "scope": scope,
            "conversation_id": conversation_id,
            "exclude_conversation_id": exclude_conversation_id,
        }

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
                        match_strength="none",
                    )
                query = parsed.get("q", query)
                filters = parsed.get("f", filters)
                scope = filters.get("scope", scope)
                conversation_id = filters.get("conversation_id", conversation_id)
                exclude_conversation_id = filters.get(
                    "exclude_conversation_id", exclude_conversation_id
                )
                offset = int(parsed.get("off", 0))
            except (json.JSONDecodeError, ValueError, TypeError):
                return SearchPage(
                    hits=[],
                    has_more=False,
                    next_cursor=None,
                    index_revision=rev,
                    cursor_expired=True,
                    match_strength="none",
                )

        compiled = compile_search_query(query)
        lane_k = max(self.lane_candidate_k, k * 4)
        lanes: list[list[str]] = []
        weights: list[float] = []
        hit_map: dict[str, Hit] = {}
        meta_map: dict[str, HitMeta] = {}

        use_kb = scope in ("all", "knowledge")
        use_conv = scope in ("all", "conversations")

        kb_fts_ids: list[str] = []
        kb_vec_ids: list[str] = []

        if use_kb:
            ids, m, mm = self._kb_fts_lane(query, lane_k)
            kb_fts_ids = ids
            if ids:
                lanes.append(ids)
                weights.append(self.lane_weights[0])
                hit_map.update(m)
                meta_map.update(mm)
            ids, m, mm = self._kb_vector_lane(
                query, lane_k, vector_text=compiled.vector_text
            )
            kb_vec_ids = ids
            if ids:
                lanes.append(ids)
                weights.append(self.lane_weights[1])
                hit_map.update(m)
                meta_map.update(mm)

        conv_lane_k = lane_k
        if (
            use_conv
            and use_kb
            and self.kb_first_throttle
            and scope == "all"
        ):
            kb_strength = assess_lane_strength(
                kb_fts_ids + kb_vec_ids,
                meta_map,
                hit_map,
                compiled=compiled,
                min_vector_score=self.min_score,
            )
            if kb_strength == "strong":
                conv_lane_k = max(1, lane_k // 3)

        if use_conv:
            ids, m, mm = self._conv_fts_lane(
                query,
                conv_lane_k,
                conversation_id=conversation_id,
                exclude_conversation_id=exclude_conversation_id,
            )
            if ids:
                lanes.append(ids)
                weights.append(self.lane_weights[2])
                hit_map.update(m)
                meta_map.update(mm)
            ids, m, mm = self._conv_vector_lane(
                query,
                conv_lane_k,
                vector_text=compiled.vector_text,
                conversation_id=conversation_id,
                exclude_conversation_id=exclude_conversation_id,
            )
            if ids:
                lanes.append(ids)
                weights.append(self.lane_weights[3])
                hit_map.update(m)
                meta_map.update(mm)

        fused = reciprocal_rank_fusion(lanes, k=self.rrf_k, weights=weights)
        page_ids = [doc_id for doc_id, _ in fused[offset : offset + k]]
        page_hits = [hit_map[doc_id] for doc_id in page_ids if doc_id in hit_map]
        page_hits = merge_adjacent_conversation_hits(page_hits)
        page_hits, match_strength = gate_page_hits(
            page_hits,
            meta_map,
            compiled=compiled,
            min_vector_score=self.min_score,
        )

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
        provenance_groups = group_provenance(
            page_hits, doc_conversation_ids=doc_conversation_ids
        )

        next_offset = offset + k
        has_more = next_offset < len(fused) and match_strength == "strong"
        next_cursor = (
            _make_cursor(query, filters, rev, next_offset) if has_more else None
        )

        return SearchPage(
            hits=page_hits,
            has_more=has_more,
            next_cursor=next_cursor,
            index_revision=rev,
            provenance_groups=provenance_groups,
            match_strength=match_strength,
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
        attachments = [s for s in sources if not is_markdown_path(s)]
        return Answer(text=text, sources=sources, attachments=attachments)
