from app.engine.usage.normalize import cached_tokens_from_usage, usage_from_resp


class _Usage:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def test_cached_tokens_openai_details():
    u = _Usage(prompt_tokens_details=_Usage(cached_tokens=12))
    assert cached_tokens_from_usage(u) == 12


def test_cached_tokens_deepseek():
    u = _Usage(prompt_cache_hit_tokens=7)
    assert cached_tokens_from_usage(u) == 7


def test_usage_from_resp():
    class Resp:
        usage = _Usage(prompt_tokens=10, completion_tokens=3, total_tokens=13)

    pt, ct, tt, cache, known = usage_from_resp(Resp())
    assert (pt, ct, tt, known) == (10, 3, 13, True)
    assert cache is None
