"""推理强度档位按模型变化。"""

from app.models.effort import default_effort, supported_efforts
from app.models.thinking import thinking_request_kwargs
from app.models.candidate import ModelCandidate


def test_gpt52_efforts_include_none_and_xhigh():
    opts = supported_efforts("gpt-5.2", "openai_kwargs")
    assert opts == ("none", "low", "medium", "high", "xhigh")
    assert default_effort("gpt-5.2", "openai_kwargs") == "none"


def test_deepseek_efforts_three():
    assert supported_efforts("deepseek-v4-pro", "deepseek") == ("low", "medium", "high")


def test_openai_kwargs_passes_xhigh():
    c = ModelCandidate(
        model="gpt-5.2",
        thinking=True,
        thinking_protocol="openai_kwargs",
        effort="xhigh",
    )
    kw = thinking_request_kwargs(c, enable=True)
    assert kw == {"reasoning_effort": "xhigh"}
