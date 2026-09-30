"""按实际正文定位 _parts 并分段；仅对多模态媒体 URL 脱敏。"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse, urlunparse

from app.engine.agent.prompt_parts import (
    PARTS_KEY,
    fallback_parts_for_message,
)
from app.logging_config import get_logger

_log = get_logger("request_segment")

_MEDIA_URL_KEYS = (
    ("image_url", "url"),
    ("video_url", "url"),
    ("input_audio", "data"),
)


def sanitize_api_message(msg: dict) -> dict:
    """深拷贝消息；仅脱敏 list content 里媒体项的 URL/data。"""
    out = dict(msg)
    content = out.get("content")
    if isinstance(content, list):
        out["content"] = [_sanitize_content_item(item) for item in content]
    return out


def _sanitize_content_item(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    out = dict(item)
    typ = out.get("type")
    if typ == "text":
        return out
    if typ == "image_url":
        inner = dict(out.get("image_url") or {})
        inner["url"] = _sanitize_media_url(str(inner.get("url") or ""))
        out["image_url"] = inner
        return out
    if typ == "video_url":
        inner = dict(out.get("video_url") or {})
        inner["url"] = _sanitize_media_url(str(inner.get("url") or ""))
        out["video_url"] = inner
        return out
    for key, sub in _MEDIA_URL_KEYS:
        if key in out and isinstance(out[key], dict):
            inner = dict(out[key])
            if sub in inner:
                inner[sub] = _sanitize_media_url(str(inner[sub]))
            out[key] = inner
    return out


def _sanitize_media_url(url: str) -> str:
    if not url:
        return url
    if url.startswith("data:"):
        kb = max(1, (len(url) + 3) // 4 // 1024)
        return f"data:…（已省略，约 {kb} KB）"
    try:
        p = urlparse(url)
        if p.scheme in ("http", "https"):
            return urlunparse((p.scheme, p.netloc, p.path, p.params, "", ""))
    except Exception:
        pass
    return url


def message_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(str(item.get("text") or ""))
        return "".join(texts)
    return str(content or "")


def annotate(text: str, parts: list[dict]) -> list[dict[str, Any]]:
    """按 parts 顺序定位，切成首尾相接覆盖全文的分段。"""
    if not text:
        return []
    if not parts:
        return [{"kind": "unlabeled", "label": "未标注", "text": text}]
    cursor = 0
    segments: list[dict[str, Any]] = []
    for part in parts:
        raw = str(part.get("text") or "")
        needle = raw.strip()
        if not needle:
            continue
        idx = text.find(needle, cursor)
        if idx < 0:
            _log.warning("request segment: part not found kind=%s", part.get("kind"))
            continue
        prefix = ""
        if idx > cursor:
            gap = text[cursor:idx]
            if gap.strip():
                segments.append(
                    {"kind": "unlabeled", "label": "未标注", "text": gap}
                )
            elif gap:
                if segments:
                    segments[-1]["text"] += gap
                else:
                    prefix = gap
        seg_text = prefix + text[idx : idx + len(needle)]
        segments.append(
            {
                "kind": part.get("kind") or "unlabeled",
                "label": part.get("label") or "未标注",
                "text": seg_text,
            }
        )
        cursor = idx + len(needle)
    if cursor < len(text):
        tail = text[cursor:]
        if tail.strip():
            segments.append({"kind": "unlabeled", "label": "未标注", "text": tail})
        elif tail and segments:
            segments[-1]["text"] += tail
    if not segments:
        return [{"kind": "unlabeled", "label": "未标注", "text": text}]
    joined = "".join(s["text"] for s in segments)
    if joined != text:
        _log.warning(
            "request segment invariant broken len=%d/%d", len(joined), len(text)
        )
        return [{"kind": "unlabeled", "label": "未标注", "text": text}]
    return segments


def _attachment_label(path: str) -> str:
    name = PurePosixPath(path.replace("\\", "/")).name or path
    return f"附件「{name}」"


def _media_type_from_content_item(item: dict) -> str:
    typ = item.get("type")
    if typ == "video_url":
        return "video"
    return "image"


def segments_for_api_message(
    msg: dict,
    annotation: dict | None,
) -> list[dict[str, Any]]:
    ann = annotation or {}
    parts = msg.get(PARTS_KEY) or ann.get("parts")
    if not parts:
        parts = fallback_parts_for_message(msg)
    text_parts = [p for p in parts if p.get("kind") != "attachment"]
    text = message_text_content(msg.get("content"))
    segs = annotate(text, list(text_parts))

    attachments = list(ann.get("attachments") or [])
    content = msg.get("content")
    att_i = 0
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                continue
            if item.get("type") not in ("image_url", "video_url") and "image_url" not in item:
                if item.get("type") not in ("input_audio",):
                    continue
            path = attachments[att_i] if att_i < len(attachments) else ""
            att_i += 1
            media_type = _media_type_from_content_item(item)
            if path:
                label = _attachment_label(path)
                name = PurePosixPath(path.replace("\\", "/")).name or path
            else:
                name = "视频" if media_type == "video" else "图片"
                label = f"附件「{name}」"
            segs.append(
                {
                    "kind": "attachment",
                    "label": label,
                    "text": "",
                    "media": {"type": media_type, "name": name, "path": path},
                }
            )
    return segs


def segment_meta_for_store(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in segments:
        meta: dict[str, Any] = {
            "kind": s["kind"],
            "label": s["label"],
            "len": len(s.get("text") or ""),
        }
        if s.get("media"):
            meta["media"] = s["media"]
        out.append(meta)
    return out


def segments_from_store_meta(
    text: str, seg_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    segments: list[dict] = []
    cursor = 0
    for meta in seg_meta:
        if meta.get("media"):
            segments.append(
                {
                    "kind": meta["kind"],
                    "label": meta["label"],
                    "text": "",
                    "media": meta["media"],
                }
            )
            continue
        ln = int(meta["len"])
        piece = text[cursor : cursor + ln]
        cursor += ln
        segments.append(
            {
                "kind": meta["kind"],
                "label": meta["label"],
                "text": piece,
            }
        )
    return segments
