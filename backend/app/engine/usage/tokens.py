"""Token 启发式估算（检查器分摊与容量展示共用）。"""

from __future__ import annotations

from app.models.media import attachment_is_video
from app.models.vision import is_vision_image_path

_VISION_TOKENS_PER_IMAGE = 765
_VISION_TOKENS_PER_VIDEO = 1000

_MESSAGE_OVERHEAD = 4


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        code = ord(ch)
        if _is_cjk(code):
            cjk += 1
        else:
            other += 1
    return int(cjk * 1.0 + other * 0.3)


def _is_cjk(code: int) -> bool:
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2CEAF
        or 0x3000 <= code <= 0x303F
        or 0xFF00 <= code <= 0xFFEF
    )


def estimate_attachment_tokens(paths: list[str]) -> int:
    if not paths:
        return 0
    total = 0
    for path in paths:
        if is_vision_image_path(path):
            total += _VISION_TOKENS_PER_IMAGE
        elif attachment_is_video(path):
            total += _VISION_TOKENS_PER_VIDEO
    return total


def message_overhead_tokens() -> int:
    return _MESSAGE_OVERHEAD
