"""模型能力目录：内置 preset；未命中保守默认（image/thinking=false）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.candidate import ImageWire, ThinkingProtocol


@dataclass(frozen=True)
class ModelCapabilities:
    image: bool = False
    thinking: bool = False
    image_wire: ImageWire = "data"
    thinking_protocol: ThinkingProtocol = "none"


# 常用模型保守预填（共识：目录未命中 → image/thinking false）
_PRESET: dict[str, ModelCapabilities] = {
    # Agnes：识图走 URL；支持 thinking
    "agnes-2.0-flash": ModelCapabilities(
        image=True, thinking=True, image_wire="url", thinking_protocol="agnes"
    ),
    "agnes-2.5-flash": ModelCapabilities(
        image=True, thinking=True, image_wire="url", thinking_protocol="agnes"
    ),
    "agnes-2.5-pro": ModelCapabilities(
        image=True, thinking=True, image_wire="url", thinking_protocol="agnes"
    ),
    "agnes-2.5-pro-alpha": ModelCapabilities(
        image=True, thinking=True, image_wire="url", thinking_protocol="agnes"
    ),
    # DeepSeek 主聊天：无识图；可思考
    "deepseek-chat": ModelCapabilities(
        image=False, thinking=True, image_wire="data", thinking_protocol="deepseek"
    ),
    "deepseek-reasoner": ModelCapabilities(
        image=False, thinking=True, image_wire="data", thinking_protocol="deepseek"
    ),
    "deepseek-v4-flash": ModelCapabilities(
        image=False, thinking=True, image_wire="data", thinking_protocol="deepseek"
    ),
    "deepseek-v4-pro": ModelCapabilities(
        image=False, thinking=True, image_wire="data", thinking_protocol="deepseek"
    ),
    # Qwen
    "qwen3.8-max": ModelCapabilities(
        image=True, thinking=True, image_wire="data", thinking_protocol="qwen"
    ),
    "qwen3-max": ModelCapabilities(
        image=True, thinking=True, image_wire="data", thinking_protocol="qwen"
    ),
    "qwen-plus": ModelCapabilities(
        image=True, thinking=True, image_wire="data", thinking_protocol="qwen"
    ),
    # OpenAI 常见
    "gpt-4o": ModelCapabilities(
        image=True, thinking=False, image_wire="data", thinking_protocol="none"
    ),
    "gpt-4o-mini": ModelCapabilities(
        image=True, thinking=False, image_wire="data", thinking_protocol="none"
    ),
    "gpt-4.1": ModelCapabilities(
        image=True, thinking=False, image_wire="data", thinking_protocol="none"
    ),
    "o3": ModelCapabilities(
        image=True, thinking=True, image_wire="data", thinking_protocol="openai_kwargs"
    ),
    "o4-mini": ModelCapabilities(
        image=True, thinking=True, image_wire="data", thinking_protocol="openai_kwargs"
    ),
}


def _normalize_model_id(model: str) -> str:
    return (model or "").strip().lower()


def lookup_capabilities(model: str, base_url: str | None = None) -> ModelCapabilities:
    mid = _normalize_model_id(model)
    if mid in _PRESET:
        return _PRESET[mid]
    # 前缀启发（仍偏保守：仅明确家族）
    if mid.startswith("agnes-"):
        return ModelCapabilities(
            image=True, thinking=True, image_wire="url", thinking_protocol="agnes"
        )
    if mid.startswith("deepseek-"):
        return ModelCapabilities(
            image=False, thinking=True, image_wire="data", thinking_protocol="deepseek"
        )
    if mid.startswith("qwen"):
        return ModelCapabilities(
            image=True, thinking=True, image_wire="data", thinking_protocol="qwen"
        )
    if "agnes-ai.com" in (base_url or "").lower():
        return ModelCapabilities(
            image=True, thinking=True, image_wire="url", thinking_protocol="agnes"
        )
    return ModelCapabilities()


def enrich_candidate_dict(item: dict[str, Any]) -> dict[str, Any]:
    """若未显式设置能力字段，用目录预填。"""
    out = dict(item)
    model = str(out.get("model") or "")
    base_url = out.get("base_url")
    caps = lookup_capabilities(model, base_url if isinstance(base_url, str) else None)
    if "image" not in out:
        out["image"] = caps.image
    if "thinking" not in out:
        out["thinking"] = caps.thinking
    if "image_wire" not in out:
        out["image_wire"] = caps.image_wire
    if "thinking_protocol" not in out:
        out["thinking_protocol"] = caps.thinking_protocol
    if "effort" not in out:
        out["effort"] = "medium"
    return out
