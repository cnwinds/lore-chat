"""推理强度档位：按模型/协议列出可选等级，并归一化用户选择。"""

from __future__ import annotations

from typing import Any, Literal

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
_ALL_EFFORT_SET = frozenset(ALL_EFFORTS)

_GENERIC_THREE: tuple[Effort, ...] = ("low", "medium", "high")
_GENERIC_WITH_MAX: tuple[Effort, ...] = ("low", "medium", "high", "max")
_OPENAI_GPT52: tuple[Effort, ...] = ("none", "low", "medium", "high", "xhigh")
_OPENAI_GPT51: tuple[Effort, ...] = ("none", "low", "medium", "high")
_OPENAI_GPT5: tuple[Effort, ...] = ("minimal", "low", "medium", "high")
_OPENAI_O: tuple[Effort, ...] = ("low", "medium", "high")
_OPENAI_BROAD: tuple[Effort, ...] = ("none", "minimal", "low", "medium", "high", "xhigh")
_GLM_EFFORTS: tuple[Effort, ...] = ("low", "medium", "high", "max")


def _norm_id(model: str) -> str:
    return (model or "").strip().lower()


def parse_reasoning_options(raw: Any) -> tuple[Effort, ...]:
    """从 models.dev / 补充文件的 reasoning_options 提取 effort 档位；不臆造。

    只认 type=effort 的 values；toggle / budget_tokens 不映射成假档位。
    """
    if not isinstance(raw, list):
        return ()
    out: list[Effort] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().lower() != "effort":
            continue
        values = item.get("values")
        if not isinstance(values, (list, tuple)):
            continue
        for v in values:
            s = str(v).strip().lower()
            if s in _ALL_EFFORT_SET and s not in seen:
                seen.add(s)
                out.append(s)  # type: ignore[arg-type]
    return tuple(out)


def pick_default_effort(options: tuple[Effort, ...], *, model: str = "") -> Effort:
    """在给定 options 内选默认；options 为空时回落 medium（仅供请求侧预算）。"""
    if not options:
        return "medium"
    mid = _norm_id(model)
    if mid.startswith("gpt-5.2") or mid.startswith("gpt-5.1"):
        if "none" in options:
            return "none"
    if "medium" in options:
        return "medium"
    return options[len(options) // 2]


def coerce_to_options(
    value: str | None,
    options: tuple[Effort, ...],
    *,
    model: str = "",
) -> Effort:
    if not options:
        return "medium"
    raw = (value or "").strip().lower()
    if raw in options:
        return raw  # type: ignore[return-value]
    return pick_default_effort(options, model=model)


def supported_efforts(model: str, protocol: str | None = None) -> tuple[Effort, ...]:
    """无目录命中时的前缀启发档位（不覆盖 models.dev / 补充文件）。"""
    mid = _norm_id(model)
    proto = (protocol or "").strip().lower()

    if proto in {"deepseek", "qwen"}:
        return _GENERIC_WITH_MAX
    # Agnes：可思考，但无对外暴露的强度档
    if proto == "agnes" or mid.startswith("agnes-"):
        return ()

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

    if mid.startswith(("deepseek-", "qwen")):
        return _GENERIC_WITH_MAX

    # 智谱 GLM 家族常见档位（含 max）
    if mid.startswith("glm") or "/glm" in f"/{mid}":
        return _GLM_EFFORTS

    # 未知：保守三档（max 仅给明确支持的协议/前缀）
    return _GENERIC_THREE


def default_effort(model: str, protocol: str | None = None) -> Effort:
    return pick_default_effort(supported_efforts(model, protocol), model=model)


def coerce_effort(value: str | None, *, model: str, protocol: str | None = None) -> Effort:
    return coerce_to_options(value, supported_efforts(model, protocol), model=model)


def format_model_label(
    model: str,
    *,
    thinking: bool,
    effort: str | None,
    effort_options: tuple[str, ...] | list[str] | None,
) -> str:
    """会话展示：开启思考且有可选强度档时为「模型 - 档位」，否则仅模型名。

    thinking 门槛：关思考时未使用推理强度，即使 settings 里仍残留档位也不展示。
    """
    name = (model or "").strip()
    if not name:
        return name
    if not thinking or not effort_options:
        return name
    ev = (effort or "").strip()
    if not ev:
        return name
    return f"{name} - {ev}"
