"""思考模式 / effort → 各厂商请求参数。"""

from __future__ import annotations

from typing import Any

from app.models.candidate import ModelCandidate, ThinkingProtocol
from app.models.effort import Effort, coerce_effort

# token budget（非 OpenAI reasoning_effort 字符串的协议使用）
_EFFORT_BUDGET: dict[str, int] = {
    "none": 0,
    "minimal": 512,
    "low": 1024,
    "medium": 2048,
    "high": 8192,
    "xhigh": 16384,
    "max": 32768,
}

_DEEPSEEK_EFFORT: dict[str, str] = {
    "none": "low",
    "minimal": "low",
    "low": "low",
    "medium": "high",
    "high": "max",
    "xhigh": "max",
    "max": "max",
}


def thinking_request_kwargs(candidate: ModelCandidate, *, enable: bool) -> dict[str, Any]:
    if not enable or not candidate.thinking:
        return {}
    proto: ThinkingProtocol = candidate.thinking_protocol
    effort: Effort = coerce_effort(
        candidate.effort, model=candidate.model, protocol=proto
    )
    budget = _EFFORT_BUDGET.get(effort, 2048)

    if proto == "none":
        return {}
    if proto == "deepseek":
        return {
            "thinking": {"type": "enabled"},
            "reasoning_effort": _DEEPSEEK_EFFORT.get(effort, "high"),
        }
    if proto == "qwen":
        if budget <= 0:
            return {"extra_body": {"enable_thinking": False}}
        return {
            "extra_body": {
                "enable_thinking": True,
                "thinking_budget": budget,
            }
        }
    if proto == "agnes":
        if budget <= 0:
            return {}
        return {
            "extra_body": {
                "chat_template_kwargs": {"enable_thinking": True},
            },
            "thinking": {"type": "enabled", "budget_tokens": budget},
        }
    if proto == "openai_kwargs":
        # GPT-5.2 等：原样传递 none|minimal|low|medium|high|xhigh
        return {"reasoning_effort": effort}
    return {}
