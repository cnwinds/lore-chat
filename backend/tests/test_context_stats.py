"""上下文容量：读请求快照或回落用量。"""

from app.engine.usage.context_stats import build_context_stats
from app.engine.usage.request_log import RequestLogRecorder, RequestLogStore
from app.engine.usage.request_capture import request_capture_context
from app.engine.usage.tokens import estimate_tokens


class _Usage:
    def __init__(self, last_prompt=100, last_model="m1"):
        self._last_prompt = last_prompt
        self._last_model = last_model

    def conversation_usage_totals(self, _cid: str) -> dict:
        return {
            "last_prompt_tokens": self._last_prompt,
            "last_model": self._last_model,
            "cache_tokens": 0,
            "prompt_tokens": 0,
            "cost_total": None,
            "turns_with_usage": 1,
        }


class _Models:
    def context_limit(self, _model, _provider):
        return 128000


def test_estimate_tokens_cjk_heavier_than_latin():
    assert estimate_tokens("你") == 1
    assert estimate_tokens("abcd") == 1


def test_context_stats_fallback_usage(tmp_path):
    body = build_context_stats(
        conversation={"id": "c1", "messages": []},
        usage_store=_Usage(42),
        models_dev=_Models(),
        chat_models=[{"model": "m1", "provider": ""}],
        request_log_store=None,
    )
    assert body["context"]["used_tokens"] == 42
    assert body["segments"] == []
    assert body["latest_call_id"] is None


def test_context_stats_from_capture(tmp_path):
    store = RequestLogStore(tmp_path / "r.db")
    rec = RequestLogRecorder(store)
    msg = [{"role": "user", "content": "hello"}]
    with request_capture_context(conversation_id="c1", turn_id="t1", round=1):
        call_id = rec.begin(
            model="m",
            model_label="M",
            candidate_id="c",
            api_messages=msg,
            annotations=[{"parts": [{"kind": "user_text", "label": "主人", "text": "hello"}]}],
            tools=None,
            params={},
        )
        rec.finish(call_id, status="ok", prompt_tokens=99)
    body = build_context_stats(
        conversation={"id": "c1", "messages": []},
        usage_store=_Usage(1),
        models_dev=_Models(),
        chat_models=[{"model": "m", "provider": ""}],
        request_log_store=store,
    )
    assert body["context"]["used_tokens"] == 99
    assert body["latest_call_id"] == call_id
    assert sum(s["tokens"] for s in body["segments"]) > 0
