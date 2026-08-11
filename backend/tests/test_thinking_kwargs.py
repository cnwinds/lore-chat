"""thinking 协议参数必须能被 OpenAI SDK create(**kwargs) 接受。"""

from __future__ import annotations

from app.models.candidate import ModelCandidate
from app.models.thinking import thinking_request_kwargs


def test_deepseek_thinking_uses_extra_body_not_top_level():
    c = ModelCandidate(
        model="deepseek-v4-flash-0731",
        thinking=True,
        thinking_protocol="deepseek",
        effort="medium",
    )
    kw = thinking_request_kwargs(c, enable=True)
    assert "thinking" not in kw
    assert kw.get("extra_body", {}).get("thinking") == {"type": "enabled"}
    assert "reasoning_effort" in (kw.get("extra_body") or kw)


def test_agnes_thinking_uses_extra_body_not_top_level():
    c = ModelCandidate(
        model="agnes-2.5-pro",
        thinking=True,
        thinking_protocol="agnes",
        effort="medium",
    )
    kw = thinking_request_kwargs(c, enable=True)
    assert "thinking" not in kw
    body = kw.get("extra_body") or {}
    assert body.get("thinking", {}).get("type") == "enabled"
    assert "chat_template_kwargs" in body


def test_openai_kwargs_still_top_level_reasoning_effort():
    c = ModelCandidate(
        model="gpt-5.2",
        thinking=True,
        thinking_protocol="openai_kwargs",
        effort="high",
    )
    assert thinking_request_kwargs(c, enable=True) == {"reasoning_effort": "high"}
