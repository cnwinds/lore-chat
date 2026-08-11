"""推理强度档位按模型变化。"""

from app.models.candidate import ModelCandidate
from app.models.effort import (
    default_effort,
    parse_reasoning_options,
    pick_default_effort,
    supported_efforts,
)
from app.models.thinking import thinking_request_kwargs


def test_gpt52_efforts_include_none_and_xhigh():
    opts = supported_efforts("gpt-5.2", "openai_kwargs")
    assert opts == ("none", "low", "medium", "high", "xhigh")
    assert default_effort("gpt-5.2", "openai_kwargs") == "none"


def test_deepseek_efforts_three():
    assert supported_efforts("deepseek-v4-pro", "deepseek") == ("low", "medium", "high")


def test_agnes_efforts_empty():
    assert supported_efforts("agnes-2.5-pro", "agnes") == ()


def test_openai_kwargs_passes_xhigh():
    c = ModelCandidate(
        model="gpt-5.2",
        thinking=True,
        thinking_protocol="openai_kwargs",
        effort="xhigh",
    )
    kw = thinking_request_kwargs(c, enable=True)
    assert kw == {"reasoning_effort": "xhigh"}


def test_parse_reasoning_options_effort_only():
    opts = parse_reasoning_options(
        [
            {"type": "toggle"},
            {"type": "effort", "values": ["low", "bogus", "high"]},
            {"type": "budget_tokens", "min": 1024},
        ]
    )
    assert opts == ("low", "high")


def test_pick_default_effort_empty_is_medium():
    assert pick_default_effort(()) == "medium"


def test_format_model_label_with_and_without_effort():
    from app.models.effort import format_model_label

    assert (
        format_model_label(
            "deepseek-v4-flash-0731",
            thinking=True,
            effort="high",
            effort_options=("low", "medium", "high"),
        )
        == "deepseek-v4-flash-0731 - high"
    )
    assert (
        format_model_label(
            "agnes-2.5-pro",
            thinking=True,
            effort="medium",
            effort_options=(),
        )
        == "agnes-2.5-pro"
    )
    assert (
        format_model_label(
            "gpt-4o",
            thinking=False,
            effort="medium",
            effort_options=("low", "medium", "high"),
        )
        == "gpt-4o"
    )


def test_display_label_uses_candidate_effort_options():
    from app.models.candidate import ModelCandidate
    from app.models.llm import _display_model_label

    deepseek = ModelCandidate(
        model="deepseek-v4-flash-0731",
        thinking=True,
        effort="high",
        effort_options=["low", "medium", "high"],
    )
    assert _display_model_label(deepseek) == "deepseek-v4-flash-0731 - high"

    agnes = ModelCandidate(
        model="agnes-2.5-pro",
        thinking=True,
        effort="medium",
        effort_options=[],
    )
    assert _display_model_label(agnes) == "agnes-2.5-pro"
