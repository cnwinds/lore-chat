from __future__ import annotations

from app.index.types import Hit


def conversation_ids_from_meta(meta: dict) -> list[str]:
    ids = meta.get("conversation_ids")
    if isinstance(ids, list):
        return [str(x) for x in ids if x]
    legacy = meta.get("conversation_id")
    return [str(legacy)] if legacy else []


def merge_adjacent_conversation_hits(hits: list[Hit]) -> list[Hit]:
    conv_hits = [h for h in hits if h.message_id is not None]
    other = [h for h in hits if h.message_id is None]
    conv_hits.sort(key=lambda h: (h.source, h.message_id or "", h.start_char or 0))
    merged: list[Hit] = []
    for h in conv_hits:
        if (
            merged
            and merged[-1].message_id == h.message_id
            and merged[-1].source == h.source
            and merged[-1].end_char == h.start_char
        ):
            prev = merged[-1]
            merged[-1] = Hit(
                doc_id=prev.doc_id,
                chunk=prev.chunk + h.chunk,
                score=max(prev.score, h.score),
                source=prev.source,
                message_id=prev.message_id,
                start_char=prev.start_char,
                end_char=h.end_char,
                offset_version=prev.offset_version,
            )
        else:
            merged.append(h)
    return other + merged


def group_provenance(
    hits: list[Hit],
    *,
    doc_conversation_ids: dict[str, list[str]],
) -> list[dict]:
    buckets: dict[str, list[Hit]] = {}
    for h in hits:
        if h.source.startswith("conv:"):
            cid = h.source[5:]
            buckets.setdefault(f"conversation:{cid}", []).append(h)
        elif h.source in doc_conversation_ids:
            for cid in doc_conversation_ids[h.source]:
                buckets.setdefault(f"conversation:{cid}", []).append(h)
    groups: list[dict] = []
    for key, group_hits in buckets.items():
        if len(group_hits) < 2:
            continue
        has_summary = any(not gh.source.startswith("conv:") for gh in group_hits)
        has_message = any(gh.source.startswith("conv:") for gh in group_hits)
        if has_summary and has_message:
            groups.append({
                "group_key": key,
                "nav_preference": "summary",
                "hits": group_hits,
            })
    return groups
