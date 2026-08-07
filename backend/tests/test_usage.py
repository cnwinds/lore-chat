"""用量模块：存储、计价、聚合。"""

from datetime import datetime, timezone

from app.engine.usage.recorder import UsageRecorder, compute_cost
from app.engine.usage.store import UsageStore


def test_compute_cost_chat():
    assert compute_cost(
        kind="chat",
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        prompt_per_1k=0.001,
        completion_per_1k=0.002,
        embed_per_1k=None,
    ) == 0.002


def test_compute_cost_unpriced():
    assert (
        compute_cost(
            kind="chat",
            prompt_tokens=100,
            completion_tokens=100,
            total_tokens=200,
            prompt_per_1k=None,
            completion_per_1k=None,
            embed_per_1k=None,
        )
        is None
    )


def test_usage_store_record_and_summary(tmp_path):
    store = UsageStore(tmp_path / "usage.db")
    rec = UsageRecorder(store)
    store.upsert_price("m1", prompt_per_1k=1.0, completion_per_1k=2.0)
    eid = rec.record(
        model="m1",
        kind="chat",
        role="small",
        prompt_tokens=1000,
        completion_tokens=1000,
        total_tokens=2000,
        tokens_known=True,
        status="ok",
        duration_ms=12,
        conversation_id="c1",
    )
    assert eid
    prices = store.list_prices()
    assert any(p["model"] == "m1" for p in prices)

    start = "2000-01-01T00:00:00+00:00"
    end = "2100-01-01T00:00:00+00:00"
    summary = store.summarize(granularity="month", start=start, end=end)
    assert summary["totals"]["calls"] == 1
    assert summary["totals"]["total_tokens"] == 2000
    assert summary["totals"]["cost"] == 3.0
    assert summary["by_model"][0]["model"] == "m1"

    events = store.list_events(limit=10)
    assert events[0]["conversation_id"] == "c1"
    assert events[0]["tokens_known"] == 1


def test_usage_unknown_tokens_no_fake_cost(tmp_path):
    store = UsageStore(tmp_path / "usage.db")
    rec = UsageRecorder(store)
    store.upsert_price("m2", prompt_per_1k=1.0, completion_per_1k=1.0)
    rec.record(
        model="m2",
        kind="stream_tools",
        role="big",
        tokens_known=False,
        status="ok",
    )
    events = store.list_events()
    assert events[0]["cost"] is None
    assert events[0]["tokens_known"] == 0


def test_usage_error_recorded(tmp_path):
    store = UsageStore(tmp_path / "usage.db")
    rec = UsageRecorder(store)
    rec.record(
        model="m3",
        kind="chat",
        status="error",
        error="boom",
        duration_ms=5,
    )
    ev = store.list_events()[0]
    assert ev["status"] == "error"
    assert ev["error"] == "boom"


def test_ensure_model_on_insert(tmp_path):
    store = UsageStore(tmp_path / "usage.db")
    rec = UsageRecorder(store)
    rec.record(model="new-model", kind="embed", role="embed", status="ok")
    assert any(p["model"] == "new-model" for p in store.list_prices())


def test_bucket_week_monday(tmp_path):
    store = UsageStore(tmp_path / "usage.db")
    # 2026-08-07 is Friday → ISO week 32
    store.insert_event(
        {
            "ts": datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc).isoformat(),
            "model": "m",
            "kind": "chat",
            "tokens_known": 0,
            "status": "ok",
        }
    )
    summary = store.summarize(
        granularity="week",
        start="2026-01-01T00:00:00+00:00",
        end="2027-01-01T00:00:00+00:00",
        timezone_name="Asia/Shanghai",
    )
    assert summary["by_bucket"][0]["bucket"] == "2026-W32"
