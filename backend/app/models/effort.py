"""推理强度档位：按模型/协议列出可选等级，并归一化用户选择。"""

from __future__ import annotations

from typing import Literal

# 跨厂商并集；具体模型只暴露自己支持的子集
Effort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]

ALL_EFFORTS: tuple[Effort, ...] = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

_GENERIC_THREE: tuple[Effort, ...] = ("low", "medium", "high")
_OPENAI_GPT52: tuple[Effort, ...] = ("none", "low", "medium", "high", "xhigh")
_OPENAI_GPT51: tuple[Effort, ...] = ("none", "low", "medium", "high")
_OPENAI_GPT5: tuple[Effort, ...] = ("minimal", "low", "medium", "high")
_OPENAI_O: tuple[Effort, ...] = ("low", "medium", "high")
_OPENAI_BROAD: tuple[Effort, ...] = ("none", "minimal", "low", "medium", "high", "xhigh")


def _norm_id(model: str) -> str:
    return (model or "").strip().lower()


def supported_efforts(model: str, protocol: str | None = None) -> tuple[Effort, ...]:
    """返回该模型可选的推理强度（有序）。"""
    mid = _norm_id(model)
    proto = (protocol or "").strip().lower()

    if proto in {"deepseek", "qwen", "agnes"}:
        return _GENERIC_THREE

    # OpenAI GPT-5.x 家族（含 codex / pro / instant 等后缀）
    if mid.startswith("gpt-5.2") or "/gpt-5.2" in mid:
        return _OPENAI_GPT52
    if mid.startswith("gpt-5.1") or "/gpt-5.1" in mid:
        return _OPENAI_GPT51
    if mid.startswith("gpt-5") or "/gpt-5" in mid:
        return _OPENAI_GPT5

    if mid.startswith(("o1", "o3", "o4")) or any(
        f"/{p}" in f"/{mid}" for p in ("o1", "o3", "o4")
    ):
        return _OPENAI_O

    if proto == "openai_kwargs":
        return _OPENAI_BROAD

    if mid.startswith(("agnes-", "deepseek-", "qwen")):
        return _GENERIC_THREE

    # 未知：保守三档，避免下拉过宽
    return _GENERIC_THREE


def default_effort(model: str, protocol: str | None = None) -> Effort:
    mid = _norm_id(model)
    opts = supported_efforts(model, protocol)
    # GPT-5.2 / 5.1 官方默认偏 none
    if mid.startswith("gpt-5.2") or mid.startswith("gpt-5.1"):
        return "none" if "none" in opts else opts[0]
    if "medium" in opts:
        return "medium"
    return opts[len(opts) // 2]


def coerce_effort(value: str | None, *, model: str, protocol: str | None = None) -> Effort:
    opts = supported_efforts(model, protocol)
    raw = (value or "").strip().lower()
    if raw in opts:
        return raw  # type: ignore[return-value]
    return default_effort(model, protocol)
