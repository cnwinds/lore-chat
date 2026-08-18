"""模型 id 规范化：OpenRouter 等网关用 vendor/model，前缀启发看全名与末段。"""

from __future__ import annotations


def normalize_model_id(model: str) -> str:
    return (model or "").strip().lower()


def model_id_tail(model: str) -> str:
    return normalize_model_id(model).rsplit("/", 1)[-1]


def model_id_has_prefix(model: str, *prefixes: str) -> bool:
    """全名或最后一段是否以任一前缀开头（无斜杠时两段相同）。"""
    mid = normalize_model_id(model)
    if not mid or not prefixes:
        return False
    tail = mid.rsplit("/", 1)[-1]
    return mid.startswith(prefixes) or tail.startswith(prefixes)
