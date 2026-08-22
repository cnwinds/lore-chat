"""Provider Adapter：Canonical MediaPart → OpenAI-compatible wire parts。"""

from __future__ import annotations

from typing import Any, Protocol

from app.models.candidate import ModelCandidate
from app.models.media import MediaPart, VideoOptions


class MediaAdapter(Protocol):
    def to_wire_parts(self, parts: list[MediaPart]) -> list[dict[str, Any]]: ...


class OpenAICompatibleMediaAdapter:
    """输出 image_url / video_url / text content parts。"""

    def to_wire_parts(self, parts: list[MediaPart]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for part in parts:
            if part.kind == "text":
                text = (part.text or "").strip()
                if text:
                    out.append({"type": "text", "text": text})
                continue
            if part.kind == "image" and part.source:
                out.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": part.source.value},
                    }
                )
                continue
            if part.kind == "video" and part.source:
                payload: dict[str, Any] = {"url": part.source.value}
                opts = part.video_options or VideoOptions()
                if opts.fps is not None:
                    payload["fps"] = opts.fps
                if opts.max_frames is not None:
                    payload["max_frames"] = opts.max_frames
                if opts.detail:
                    payload["detail"] = opts.detail
                out.append({"type": "video_url", "video_url": payload})
        return out


def get_media_adapter(_candidate: ModelCandidate) -> MediaAdapter:
    return OpenAICompatibleMediaAdapter()
