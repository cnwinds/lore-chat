"""ImageGen 内部契约与错误分类。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

AspectRatio = Literal["1:1", "16:9", "9:16", "4:3", "3:4"]

ASPECT_RATIOS: frozenset[str] = frozenset({"1:1", "16:9", "9:16", "4:3", "3:4"})
DEFAULT_ASPECT_RATIO: AspectRatio = "1:1"

Destination = Literal["chat_attachment", "kb"]


class ImageGenErrorKind(str, Enum):
    TRANSIENT = "transient"
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    SAFETY = "safety"
    INVALID_REQUEST = "invalid_request"
    UNKNOWN = "unknown"


# 仅供给侧故障可切厂商（ADR）
FAILOVER_KINDS = frozenset(
    {
        ImageGenErrorKind.TRANSIENT,
        ImageGenErrorKind.RATE_LIMIT,
    }
)


class ImageGenError(Exception):
    def __init__(self, message: str, *, kind: ImageGenErrorKind):
        self.kind = kind
        super().__init__(message)


@dataclass(frozen=True)
class ImageGenRequest:
    prompt: str
    aspect_ratio: AspectRatio = DEFAULT_ASPECT_RATIO


@dataclass(frozen=True)
class GeneratedImage:
    """厂商适配器产出：尚未落盘的像素。"""

    data: bytes
    content_type: str = "image/png"
    extension: str = "png"
    # 路由选出的厂家（并行生图时勿依赖 ImageGen 实例可变字段）
    provider: str | None = None
    provider_id: str | None = None
