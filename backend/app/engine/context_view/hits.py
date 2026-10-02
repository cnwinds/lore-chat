"""检索命中附加 lore:// uri 与 kind。"""

from __future__ import annotations

from app.engine.context_view.errors import NotFound
from app.engine.context_view.kb_kind import classify
from app.engine.context_view.scope import ViewScope
from app.engine.context_view.uri import ConversationUri, format_uri
from app.index.types import Hit


def _conversation_bucket_or_none(scope: ViewScope, cid: str) -> tuple[str, str | None] | None:
    try:
        return scope.conversation_bucket(cid)
    except (KeyError, NotFound):
        return None


def enrich_hit(scope: ViewScope, hit: Hit) -> dict | None:
    out = hit.to_dict()
    src = hit.source or ""
    if src.startswith("conv:"):
        cid = src[5:]
        bucket_owner = _conversation_bucket_or_none(scope, cid)
        if bucket_owner is None:
            return None
        bucket, owner = bucket_owner
        uri = ConversationUri(
            bucket=bucket,  # type: ignore[arg-type]
            owner=owner,
            conversation_id=cid,
            message_id=hit.message_id,
            is_dir=hit.message_id is None,
        )
        out["uri"] = format_uri(uri)
        out["kind"] = "message"
    else:
        rel = src.replace("\\", "/").lstrip("/")
        out["uri"] = f"lore://kb/{rel}"
        out["kind"] = classify(rel)
    return out


def hit_source(h) -> dict:
    if isinstance(h.source, str) and h.source.startswith("conv:"):
        out: dict = {
            "type": "conversation",
            "cid": h.source[5:],
            "excerpt": h.chunk[:240],
        }
        if h.message_id is not None:
            out["message_id"] = h.message_id
            out["start_char"] = h.start_char
            out["end_char"] = h.end_char
            out["offset_version"] = h.offset_version or "unicode-codepoint-v1"
        if h.role:
            out["role"] = h.role
        if h.ts:
            out["ts"] = h.ts
        if h.conversation_title:
            out["conversation_title"] = h.conversation_title
        return out
    return {"type": "kb", "path": h.source, "excerpt": h.chunk[:200]}


def enrich_source(scope: ViewScope, source: dict) -> dict | None:
    """与 hit_source 字段对齐的 sources 项。"""
    out = dict(source)
    stype = out.get("type")
    if stype == "conversation":
        cid = out.get("cid") or ""
        if not cid:
            return out
        bucket_owner = _conversation_bucket_or_none(scope, cid)
        if bucket_owner is None:
            return None
        bucket, owner = bucket_owner
        mid = out.get("message_id")
        uri = ConversationUri(
            bucket=bucket,  # type: ignore[arg-type]
            owner=owner,
            conversation_id=cid,
            message_id=mid,
            is_dir=mid is None,
        )
        out["uri"] = format_uri(uri)
        out.setdefault("kind", "message")
    elif stype == "kb":
        path = out.get("path") or ""
        out["uri"] = f"lore://kb/{path.replace(chr(92), '/').lstrip('/')}"
        out.setdefault("kind", classify(path))
    return out


def pair_hit_and_source(scope: ViewScope, hit: Hit) -> tuple[dict, dict] | None:
    src = hit_source(hit)
    if src.get("type") == "conversation":
        cid = src.get("cid") or ""
        if _conversation_bucket_or_none(scope, cid) is None:
            return None
    enriched_hit = enrich_hit(scope, hit)
    if enriched_hit is None:
        return None
    enriched_src = enrich_source(scope, src)
    if enriched_src is None:
        return None
    return enriched_hit, enriched_src
