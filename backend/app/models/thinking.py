"""思考模式 / effort → 各厂商请求参数。"""

from __future__ import annotations

from typing import Any

from app.models.candidate import Effort, ModelCandidate, ThinkingProtocol

_EFFORT_BUDGET: dict[Effort, int] = {
    "low": 1024,
    "medium": 2048,
    "high": 8192,
}

_DEEPSEEK_EFFORT: dict[Effort, str] = {
    "low": "low",
    "medium": "high",
    "high": "max",
}


def thinking_request_kwargs(candidate: ModelCandidate, *, enable: bool) -> dict[str, Any]:
    if not enable or not candidate.thinking:
        return {}
    proto: ThinkingProtocol = candidate.thinking_protocol
    effort: Effort = candidate.effort
    budget = _EFFORT_BUDGET[effort]

    if proto == "none":
        return {}
    if proto == "deepseek":
        return {
            "thinking": {"type": "enabled"},
            "reasoning_effort": _DEEPSEEK_EFFORT[effort],
        }
    if proto == "qwen":
        return {
            "extra_body": {
                "enable_thinking": True,
                "thinking_budget": budget,
            }
        }
    if proto == "agnes":
        return {
            "extra_body": {
                "chat_template_kwargs": {"enable_thinking": True},
            },
            # Anthropic-compatible path also accepted by some gateways
            "thinking": {"type": "enabled", "budget_tokens": budget},
        }
    if proto == "openai_kwargs":
        return {"reasoning_effort": effort}
    return {}
