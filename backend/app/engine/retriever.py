from __future__ import annotations

import base64
import json
from collections.abc import Sequence
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
from app.index.conversation_index import CONV_FAMILY, CONV_PARTITION, OFFSET_VERSION
from app.index.kb_index import KB_FAMILY, KB_PARTITION
from app.index.partitioned import (
    MetaFilter,
    PartitionTuning,
    SearchIndex,
)
from app.index.revision import IndexRevision
from app.index.search_query import compile_search_query
from app.index.types import Hit
from app.logging_config import get_logger
from app.models.llm import LLMClient
from app.engine.knowledge_writer import is_markdown_path
from app.time import normalize_search_ts, ts_in_search_range

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
        search_index: SearchIndex,
        llm: LLMClient,
        *,
        excluded_prefixes: tuple[str, ...] = (),
        min_score: float = MIN_VECTOR_SCORE,
        index_revision: IndexRevision | None = None,
        rrf_k: int = 60,
        lane_candidate_k: int = 20,
        lane_weights: tuple[float, float, float, float] = DEFAULT_LANE_WEIGHTS,
        kb_first_throttle: bool = True,
        repo=None,
        conversations=None,
    ):
        self.search_index = search_index
        self.llm = llm
        self.excluded_prefixes = tuple(excluded_prefixes)
        self.min_score = min_score
        self.index_revision = index_revision
        self.rrf_k = rrf_k
        self.lane_candidate_k = lane_candidate_k
        self.lane_weights = lane_weights
        self.kb_first_throttle = kb_first_throttle
        self.repo = repo
        self.conversations = conversations

    def _excluded(self, source: str) -> bool:
        norm = (source or "").replace("\\", "/").lstrip("/")
        return any(norm.startswith(p) for p in self.excluded_prefixes)

    @staticmethod
    def _conversation_hit_from_search(sh, *, score: float) -> Hit:
        meta = sh.meta
        cid = str(meta.get("conversation_id") or "")
        role = str(meta.get("role") or "")
        ts = str(meta.get("ts") or "")
        title = str(meta.get("conversation_title") or "")
        return Hit(
            doc_id=sh.item_id,
            chunk=sh.text,
            score=score,
            source=f"conv:{cid}",
            message_id=str(meta.get("message_id") or ""),
            start_char=int(meta.get("start_char") or 0),
            end_char=int(meta.get("end_char") or 0),
            offset_version=str(meta.get("offset_version") or OFFSET_VERSION),
            role=role or None,
            ts=ts or None,
            conversation_title=title or None,
        )

    @staticmethod
    def _conv_meta_filters(
        *,
        conversation_id: str | None,
        exclude_conversation_id: str | None,
        ts_after: str | None,
        ts_before: str | None,
    ) -> list[MetaFilter]:
        filters: list[MetaFilter] = []
        if conversation_id:
            filters.append(MetaFilter("conversation_id", "eq", conversation_id))
        elif exclude_conversation_id:
            filters.append(MetaFilter("conversation_id", "ne", exclude_conversation_id))
        if ts_after:
            filters.append(MetaFilter("ts", "gte", ts_after))
        if ts_before:
            filters.append(MetaFilter("ts", "lt", ts_before))
        return filters

    @staticmethod
    def _dedup_hits(hits: list[Hit]) -> list[Hit]:
        best: dict[str, Hit] = {}
        for h in hits:
            if h.doc_id in best and best[h.doc_id].score >= h.score:
                continue
            best[h.doc_id] = h
        return list(best.values())

    @staticmethod
    def _kb_hit_from_search(sh, *, score: float) -> Hit:
        source = str(sh.meta.get("source") or "")
        return Hit(doc_id=source, chunk=sh.text, score=score, source=source)

    def _kb_lanes(
        self,
        query: str,
        lane_k: int,
        *,
        vector_text: str,
        kb_prefixes: Sequence[str] | None = None,
    ) -> tuple[
        tuple[list[str], dict[str, Hit], dict[str, HitMeta]],
        tuple[list[str], dict[str, Hit], dict[str, HitMeta]],
    ]:
        empty: tuple[list[str], dict[str, Hit], dict[str, HitMeta]] = ([], {}, {})
        try:
            res = self.search_index.search(
                query,
                partitions=[KB_PARTITION],
                limit=lane_k,
                tunings={
                    KB_FAMILY: PartitionTuning(
                        fts_k=lane_k,
                        vec_k=lane_k,
                        min_vector_score=self.min_score,
                    )
                },
                fts_mode="keywords",
                vector_text=vector_text,
                group_prefixes=kb_prefixes,
            )
        except Exception:
            get_logger("retriever").warning("知识库检索失败", exc_info=True)
            return empty, empty

        fts_tier = res.fts_tiers.get(KB_FAMILY, "none")
        fts_hits: list[Hit] = []
        for sh in res.lanes.get(f"{KB_FAMILY}:fts", []):
            source = str(sh.meta.get("source") or "")
            if self._excluded(source):
                continue
            bm25 = sh.bm25 if sh.bm25 is not None else 0.0
            fts_hits.append(self._kb_hit_from_search(sh, score=bm25))
        fts_hits = self._dedup_hits(fts_hits)
        fts_hits.sort(key=lambda h: h.score, reverse=True)
        fts_map = {h.doc_id: h for h in fts_hits}
        fts_meta = {
            h.doc_id: HitMeta(lane="kb_fts", fts_tier=fts_tier) for h in fts_hits
        }
        fts_out = ([h.doc_id for h in fts_hits], fts_map, fts_meta)

        if res.vector_status != "ok":
            return fts_out, empty

        vec_hits: list[Hit] = []
        for sh in res.lanes.get(f"{KB_FAMILY}:vec", []):
            source = str(sh.meta.get("source") or "")
            if self._excluded(source):
                continue
            vs = sh.vector_score
            if vs is None or vs < self.min_score:
                continue
            vec_hits.append(self._kb_hit_from_search(sh, score=vs))
        vec_hits = self._dedup_hits(vec_hits)
        vec_hits.sort(key=lambda h: h.score, reverse=True)
        if should_drop_vector_lane(vec_hits):
            return fts_out, empty
        vec_map = {h.doc_id: h for h in vec_hits}
        vec_meta = {
            h.doc_id: HitMeta(lane="kb_vector", vector_score=h.score) for h in vec_hits
        }
        vec_out = ([h.doc_id for h in vec_hits], vec_map, vec_meta)
        return fts_out, vec_out

    def _conv_lanes(
        self,
        query: str,
        lane_k: int,
        *,
        vector_text: str,
        conversation_id: str | None,
        exclude_conversation_id: str | None,
        conversation_ids: Sequence[str] | None = None,
        ts_after: str | None = None,
        ts_before: str | None = None,
    ) -> tuple[
        tuple[list[str], dict[str, Hit], dict[str, HitMeta]],
        tuple[list[str], dict[str, Hit], dict[str, HitMeta]],
    ]:
        empty: tuple[list[str], dict[str, Hit], dict[str, HitMeta]] = ([], {}, {})
        if conversation_ids is not None and len(conversation_ids) == 0:
            return empty, empty
        conv_id_set: frozenset[str] | None = None
        if conversation_ids is not None:
            conv_id_set = frozenset(conversation_ids)
            filters = self._conv_meta_filters(
                conversation_id=None,
                exclude_conversation_id=None,
                ts_after=ts_after,
                ts_before=ts_before,
            )
            if len(conversation_ids) <= 1000:
                filters.append(
                    MetaFilter("conversation_id", "in", tuple(conversation_ids))
                )
        else:
            filters = self._conv_meta_filters(
                conversation_id=conversation_id,
                exclude_conversation_id=exclude_conversation_id,
                ts_after=ts_after,
                ts_before=ts_before,
            )
        try:
            res = self.search_index.search(
                query,
                partitions=[CONV_PARTITION],
                limit=lane_k,
                tunings={
                    CONV_FAMILY: PartitionTuning(
                        fts_k=lane_k,
                        vec_k=lane_k,
                        min_vector_score=self.min_score,
                    )
                },
                fts_mode="keywords",
                vector_text=vector_text,
                filters=filters,
            )
        except Exception:
            get_logger("retriever").warning("会话检索失败", exc_info=True)
            return empty, empty

        fts_tier = res.fts_tiers.get(CONV_FAMILY, "none")
        fts_hits: list[Hit] = []
        for sh in res.lanes.get(f"{CONV_FAMILY}:fts", []):
            if conv_id_set is not None and len(conversation_ids) > 1000:  # type: ignore[arg-type]
                cid = str(sh.meta.get("conversation_id") or "")
                if cid not in conv_id_set:
                    continue
            bm25 = sh.bm25 if sh.bm25 is not None else 0.0
            fts_hits.append(self._conversation_hit_from_search(sh, score=bm25))
        fts_hits = self._dedup_hits(fts_hits)
        fts_hits.sort(key=lambda h: h.score, reverse=True)
        fts_map = {h.doc_id: h for h in fts_hits}
        fts_meta = {
            h.doc_id: HitMeta(lane="conv_fts", fts_tier=fts_tier) for h in fts_hits
        }
        fts_out = ([h.doc_id for h in fts_hits], fts_map, fts_meta)

        if res.vector_status != "ok":
            return fts_out, empty

        vec_hits: list[Hit] = []
        for sh in res.lanes.get(f"{CONV_FAMILY}:vec", []):
            if conv_id_set is not None and len(conversation_ids) > 1000:  # type: ignore[arg-type]
                cid = str(sh.meta.get("conversation_id") or "")
                if cid not in conv_id_set:
                    continue
            vs = sh.vector_score
            if vs is None or vs < self.min_score:
                continue
            vec_hits.append(self._conversation_hit_from_search(sh, score=vs))
        vec_hits = self._dedup_hits(vec_hits)
        vec_hits.sort(key=lambda h: h.score, reverse=True)
        if should_drop_vector_lane(vec_hits):
            return fts_out, empty
        vec_map = {h.doc_id: h for h in vec_hits}
        vec_meta = {
            h.doc_id: HitMeta(lane="conv_vector", vector_score=h.score) for h in vec_hits
        }
        vec_out = ([h.doc_id for h in vec_hits], vec_map, vec_meta)
        return fts_out, vec_out

    def _conversation_role_ok(self, cid: str, role_id: str | None) -> bool:
        if not role_id or self.conversations is None:
            return True
        try:
            return self.conversations.get_role_id(cid) == role_id
        except KeyError:
            return False

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        scope: str = "all",
        conversation_id: str | None = None,
        exclude_conversation_id: str | None = None,
        role_id: str | None = None,
        ts_after: str | None = None,
        ts_before: str | None = None,
        kb_prefixes: Sequence[str] | None = None,
        conversation_ids: Sequence[str] | None = None,
        cursor: str | None = None,
    ) -> SearchPage:
        rev = self.index_revision.get() if self.index_revision else 0
        offset = 0
        ts_after = normalize_search_ts(ts_after)
        ts_before = normalize_search_ts(ts_before)
        filters = {
            "scope": scope,
            "conversation_id": conversation_id,
            "exclude_conversation_id": exclude_conversation_id,
            "role_id": role_id,
            "ts_after": ts_after,
            "ts_before": ts_before,
            "kb_prefixes": list(kb_prefixes) if kb_prefixes else None,
            "conversation_ids": list(conversation_ids)
            if conversation_ids is not None
            else None,
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
                role_id = filters.get("role_id", role_id)
                ts_after = normalize_search_ts(filters.get("ts_after") or ts_after)
                ts_before = normalize_search_ts(filters.get("ts_before") or ts_before)
                filters["ts_after"] = ts_after
                filters["ts_before"] = ts_before
                raw_kb = filters.get("kb_prefixes")
                kb_prefixes = tuple(raw_kb) if raw_kb else None
                raw_cids = filters.get("conversation_ids")
                conversation_ids = tuple(raw_cids) if raw_cids is not None else None
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
            (ids, m, mm), (v_ids, vm, vmm) = self._kb_lanes(
                query,
                lane_k,
                vector_text=compiled.vector_text,
                kb_prefixes=kb_prefixes,
            )
            kb_fts_ids = ids
            if ids:
                lanes.append(ids)
                weights.append(self.lane_weights[0])
                hit_map.update(m)
                meta_map.update(mm)
            kb_vec_ids = v_ids
            if v_ids:
                lanes.append(v_ids)
                weights.append(self.lane_weights[1])
                hit_map.update(vm)
                meta_map.update(vmm)

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

        conv_id_set_page: frozenset[str] | None = None
        if conversation_ids is not None:
            conv_id_set_page = frozenset(conversation_ids)

        if use_conv:
            (c_fts_ids, c_fts_m, c_fts_mm), (c_vec_ids, c_vec_m, c_vec_mm) = (
                self._conv_lanes(
                    query,
                    conv_lane_k,
                    vector_text=compiled.vector_text,
                    conversation_id=conversation_id,
                    exclude_conversation_id=exclude_conversation_id,
                    conversation_ids=conversation_ids,
                    ts_after=ts_after,
                    ts_before=ts_before,
                )
            )
            if c_fts_ids:
                lanes.append(c_fts_ids)
                weights.append(self.lane_weights[2])
                hit_map.update(c_fts_m)
                meta_map.update(c_fts_mm)
            if c_vec_ids:
                lanes.append(c_vec_ids)
                weights.append(self.lane_weights[3])
                hit_map.update(c_vec_m)
                meta_map.update(c_vec_mm)

        fused = reciprocal_rank_fusion(lanes, k=self.rrf_k, weights=weights)
        page_hits: list[Hit] = []
        next_offset = offset + k
        need_skip = bool(
            role_id or ts_after or ts_before or conv_id_set_page is not None
        )

        def _keep_hit(h: Hit) -> bool:
            src = h.source or ""
            if not src.startswith("conv:"):
                return True
            cid = src[5:]
            if conv_id_set_page is not None and cid not in conv_id_set_page:
                return False
            if role_id and not self._conversation_role_ok(cid, role_id):
                return False
            if (ts_after or ts_before) and not ts_in_search_range(
                h.ts or "", ts_after, ts_before
            ):
                return False
            return True

        if need_skip:
            # 按 fused 顺序过滤，游标推进到实际消费位置，避免下页重复/空页 has_more
            consumed = offset
            for i in range(offset, len(fused)):
                consumed = i + 1
                doc_id = fused[i][0]
                h = hit_map.get(doc_id)
                if h is None or not _keep_hit(h):
                    continue
                page_hits.append(h)
                if len(page_hits) >= k:
                    break
            next_offset = consumed
        else:
            page_ids = [doc_id for doc_id, _ in fused[offset : offset + k]]
            page_hits = [hit_map[doc_id] for doc_id in page_ids if doc_id in hit_map]
            next_offset = offset + k
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
