"""多模态附件：图片 + 视频 → Canonical MediaPart → Provider wire。"""

from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.models.candidate import ModelCandidate
from app.models.vision import (
    VISION_SKIP_SUFFIXES,
    guess_mime,
    is_image_file,
    is_image_path,
    is_vision_image_path,
)

MediaKind = Literal["text", "image", "video", "file"]
MediaSourceKind = Literal["kb_path", "http_url", "data_url"]

# 与 frontend/src/utils/kbVideoUrls.ts MAX_VIDEO_UPLOAD_BYTES 对齐
MAX_VIDEO_UPLOAD_BYTES = 50 * 1024 * 1024
# data wire 超过此大小且 public_base_url 可用时优先 signed URL
MAX_VIDEO_DATA_WIRE_BYTES = 20 * 1024 * 1024

_VIDEO_SUFFIXES = {".mp4", ".mpeg", ".mpg", ".mov", ".webm", ".m4v"}


@dataclass(frozen=True)
class MediaSource:
    kind: MediaSourceKind
    value: str
    mime: str | None = None


@dataclass(frozen=True)
class VideoOptions:
    fps: float | None = None
    max_frames: int | None = None
    detail: str | None = None


@dataclass(frozen=True)
class MediaPart:
    kind: MediaKind
    source: MediaSource | None = None
    text: str | None = None
    video_options: VideoOptions | None = None


def sniff_video_mime(path: Path) -> str | None:
    try:
        head = path.read_bytes()[:32]
    except OSError:
        return None
    return sniff_video_mime_bytes(head)


def sniff_video_mime_bytes(head: bytes) -> str | None:
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "video/mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    if head.startswith(b"\x00\x00\x01\xba") or head.startswith(b"\x00\x00\x01\xb3"):
        return "video/mpeg"
    return None


def bytes_look_like_video(data: bytes, *, name: str = "") -> bool:
    if is_video_path(name):
        return True
    return sniff_video_mime_bytes(data[:32]) is not None


def is_video_path(path: str) -> bool:
    mime, _ = mimetypes.guess_type(path)
    if mime and mime.startswith("video/"):
        return True
    return Path(path).suffix.lower() in _VIDEO_SUFFIXES


def is_video_file(path: Path) -> bool:
    if is_video_path(str(path)):
        return True
    return sniff_video_mime(path) is not None


def guess_video_mime(path: str) -> str:
    sniffed = sniff_video_mime(Path(path))
    if sniffed:
        return sniffed
    mime, _ = mimetypes.guess_type(path)
    if mime and mime.startswith("video/"):
        return mime
    return "video/mp4"


def attachment_is_video(rel_path: str, *, kb_path: Path | None = None) -> bool:
    if kb_path is not None:
        abs_p = (Path(kb_path) / rel_path).resolve()
        if abs_p.is_file():
            return is_video_file(abs_p)
    return is_video_path(rel_path)


def is_signed_media_file(path: Path) -> Literal["image", "video"] | None:
    from app.models.vision import is_signed_image_file

    if is_signed_image_file(path):
        return "image"
    if sniff_video_mime(path) is not None:
        return "video"
    return None


def _classify_attachment(rel: str, kb_path: Path) -> MediaKind:
    if Path(rel).suffix.lower() in VISION_SKIP_SUFFIXES:
        return "file"
    abs_path = (kb_path / rel).resolve()
    if abs_path.is_file():
        if is_video_file(abs_path):
            return "video"
        if is_image_file(abs_path):
            return "image"
    if is_video_path(rel):
        return "video"
    if is_image_path(rel):
        return "image"
    return "file"


def _effective_wire_mode(
    *,
    wire: Literal["data", "url"],
    abs_path: Path,
    public_base_url: str | None,
    prefer_url_over_bytes: int | None,
) -> Literal["data", "url"]:
    if wire == "url":
        return "url"
    if prefer_url_over_bytes is None:
        return wire
    base = (public_base_url or "").strip()
    if not base:
        return wire
    try:
        if abs_path.stat().st_size > prefer_url_over_bytes:
            return "url"
    except OSError:
        pass
    return wire


def _resolve_wire_url(
    *,
    rel: str,
    abs_path: Path,
    wire: Literal["data", "url"],
    kb_path: Path,
    public_base_url: str | None,
    signing_secret: str,
    mime: str,
    prefer_url_over_bytes: int | None = None,
) -> str | None:
    effective = _effective_wire_mode(
        wire=wire,
        abs_path=abs_path,
        public_base_url=public_base_url,
        prefer_url_over_bytes=prefer_url_over_bytes,
    )
    if effective == "url":
        base = (public_base_url or "").strip()
        if not base:
            return None
        from app.models.media_grants import build_media_grant_url

        return build_media_grant_url(
            public_base_url=base,
            rel_path=rel,
            kb_path=kb_path,
        )
    raw = abs_path.read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _build_media_parts(
    *,
    image_rels: list[str],
    video_rels: list[str],
    candidate: ModelCandidate,
    kb_path: Path,
    public_base_url: str | None,
    signing_secret: str,
) -> list[MediaPart]:
    parts: list[MediaPart] = []
    if not candidate.video:
        video_rels = []
    if not candidate.image:
        image_rels = []

    for rel in image_rels:
        abs_path = (kb_path / rel).resolve()
        if not abs_path.is_file():
            continue
        mime = guess_mime(str(abs_path))
        url = _resolve_wire_url(
            rel=rel,
            abs_path=abs_path,
            wire=candidate.image_wire,
            kb_path=kb_path,
            public_base_url=public_base_url,
            signing_secret=signing_secret,
            mime=mime,
        )
        if not url:
            continue
        kind: MediaSourceKind = "http_url" if url.startswith("http") else "data_url"
        parts.append(
            MediaPart(
                kind="image",
                source=MediaSource(kind=kind, value=url, mime=mime),
            )
        )

    for rel in video_rels:
        abs_path = (kb_path / rel).resolve()
        if not abs_path.is_file():
            continue
        mime = guess_video_mime(str(abs_path))
        url = _resolve_wire_url(
            rel=rel,
            abs_path=abs_path,
            wire=candidate.video_wire,
            kb_path=kb_path,
            public_base_url=public_base_url,
            signing_secret=signing_secret,
            mime=mime,
            prefer_url_over_bytes=MAX_VIDEO_DATA_WIRE_BYTES,
        )
        if not url:
            continue
        kind = "http_url" if url.startswith("http") else "data_url"
        parts.append(
            MediaPart(
                kind="video",
                source=MediaSource(kind=kind, value=url, mime=mime),
            )
        )
    return parts


def build_user_content_with_media(
    text: str,
    attachment_paths: list[str],
    *,
    candidate: ModelCandidate,
    kb_path: Path,
    public_base_url: str | None,
    signing_secret: str,
) -> str | list[dict[str, Any]]:
    """返回 OpenAI-style content：无 multimodal 则纯字符串；否则 parts 列表。"""
    image_rels: list[str] = []
    video_rels: list[str] = []
    other: list[str] = []
    dropped_videos: list[str] = []
    dropped_images: list[str] = []

    max_videos = max(1, int(candidate.max_videos or 1))
    max_images = candidate.max_images
    seen_videos = 0
    seen_images = 0

    for p in attachment_paths:
        kind = _classify_attachment(p, kb_path)
        if kind == "image" and is_vision_image_path(p):
            if max_images is not None and max_images > 0 and seen_images >= max_images:
                dropped_images.append(p)
            else:
                image_rels.append(p)
                seen_images += 1
        elif kind == "video":
            if seen_videos < max_videos:
                video_rels.append(p)
                seen_videos += 1
            else:
                dropped_videos.append(p)
        elif kind == "image":
            other.append(p)
        else:
            other.append(p)

    footnotes: list[str] = []
    if other:
        footnotes.append("（附件：" + "、".join(other) + "）")
    if dropped_images:
        footnotes.append(
            "（图片附件超出本消息上限未能送入模型：" + "、".join(dropped_images) + "）"
        )
    if dropped_videos:
        footnotes.append(
            "（视频附件超出本消息上限未能送入模型：" + "、".join(dropped_videos) + "）"
        )
    if image_rels and not candidate.image:
        footnotes.append(
            "（图片附件未能送入模型：" + "、".join(image_rels) + "）"
        )
        image_rels = []
    if video_rels and not candidate.video:
        footnotes.append(
            "（视频附件未能送入模型：" + "、".join(video_rels) + "）"
        )
        video_rels = []

    body_parts = footnotes + [text]
    body = "\n\n".join(p for p in body_parts if p)

    media_parts = _build_media_parts(
        image_rels=image_rels,
        video_rels=video_rels,
        candidate=candidate,
        kb_path=kb_path,
        public_base_url=public_base_url,
        signing_secret=signing_secret,
    )

    if not media_parts:
        return body

    from app.models.media_adapters import get_media_adapter

    adapter = get_media_adapter()
    wire = adapter.to_wire_parts(
        [MediaPart(kind="text", text=body), *media_parts]
    )
    if len(wire) == 1 and wire[0].get("type") == "text":
        return str(wire[0].get("text") or body)
    return wire


def messages_need_multimodal(
    messages: list[dict],
    *,
    kb_path: Path | None,
    kind: Literal["image", "video"],
) -> bool:
    """路由用：消息是否含需识图/视频的附件或已物化 wire part。"""
    root = kb_path
    wire_type = "video_url" if kind == "video" else "image_url"
    for m in messages:
        atts = m.get("attachments")
        if isinstance(atts, list):
            for p in atts:
                if not isinstance(p, str):
                    continue
                if kind == "video":
                    if root is not None:
                        if attachment_is_video(p, kb_path=root):
                            return True
                    elif attachment_is_video(p):
                        return True
                else:
                    if Path(p).suffix.lower() == ".svg":
                        continue
                    if root is not None:
                        abs_p = (root / p).resolve()
                        if abs_p.is_file() and is_image_file(abs_p):
                            return True
                    if is_image_path(p):
                        return True
        content = m.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == wire_type:
                    return True
    return False
