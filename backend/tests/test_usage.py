"""用量模块：存储、计价、聚合。"""

from datetime import datetime, timezone

from app.engine.usage.recorder import UsageRecorder, compute_cost
from app.engine.usage.store import UsageStore


def test_compute_cost_chat():
    # 1000 in @ 1/M + 500 out @ 2/M = 0.001 + 0.001 = 0.002
    assert compute_cost(
        kind="chat",
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        prompt_per_1m=1.0,
        completion_per_1m=2.0,
        embed_per_1m=None,
    ) == 0.002


def test_compute_cost_with_cache_input():
    # 800 cache @ 0.1/M + 200 uncached @ 1/M + 500 out @ 2/M
    assert compute_cost(
        kind="chat",
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        cache_tokens=800,
        prompt_per_1m=1.0,
        completion_per_1m=2.0,
        cache_input_per_1m=0.1,
        embed_per_1m=None,
    ) == 0.00128


def test_compute_cost_cache_falls_back_to_input():
    assert compute_cost(
        kind="chat",
        prompt_tokens=1000,
        completion_tokens=0,
        total_tokens=1000,
        cache_tokens=400,
        prompt_per_1m=1.0,
        completion_per_1m=2.0,
        cache_input_per_1m=None,
        embed_per_1m=None,
    ) == 0.001


def test_compute_cost_unpriced():
    assert (
        compute_cost(
            kind="chat",
            prompt_tokens=100,
            completion_tokens=100,
            total_tokens=200,
            prompt_per_1m=None,
            completion_per_1m=None,
            embed_per_1m=None,
        )
        is None
    )


def test_usage_store_record_and_summary(tmp_path):
    store = UsageStore(tmp_path / "usage.db")
    rec = UsageRecorder(store)
    store.upsert_price(
        "m1",
        prompt_per_1m=1000.0,
        completion_per_1m=2000.0,
        cache_input_per_1m=100.0,
    )
    eid = rec.record(
        model="m1",
        kind="chat",
        role="small",
        prompt_tokens=1000,
        completion_tokens=1000,
        total_tokens=2000,
        cache_tokens=400,
        tokens_known=True,
        status="ok",
        duration_ms=12,
        conversation_id="c1",
    )
    assert eid
    prices = store.list_prices()
    assert any(p["model"] == "m1" for p in prices)
    assert prices[0]["cache_input_per_1m"] == 100.0

    start = "2000-01-01T00:00:00+00:00"
    end = "2100-01-01T00:00:00+00:00"
    summary = store.summarize(granularity="month", start=start, end=end)
    assert summary["totals"]["calls"] == 1
    assert summary["totals"]["total_tokens"] == 2000
    assert summary["totals"]["cache_tokens"] == 400
    # 600/1M*1000 + 400/1M*100 + 1000/1M*2000 = 0.6 + 0.04 + 2 = 2.64
    assert summary["totals"]["cost"] == 2.64
    assert summary["by_model"][0]["model"] == "m1"

    events = store.list_events(limit=10)
    assert events[0]["conversation_id"] == "c1"
    assert events[0]["tokens_known"] == 1
    assert events[0]["cache_tokens"] == 400


def test_migrate_per_1k_to_per_1m(tmp_path):
    db = tmp_path / "legacy.db"
    conn = __import__("sqlite3").connect(str(db))
    conn.executescript(
        """
        CREATE TABLE model_prices (
            model TEXT PRIMARY KEY,
            prompt_per_1k REAL,
            completion_per_1k REAL,
            embed_per_1k REAL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE usage_events (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            model TEXT NOT NULL,
            kind TEXT NOT NULL,
            role TEXT,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            tokens_known INTEGER NOT NULL DEFAULT 0,
            prompt_price_per_1k REAL,
            completion_price_per_1k REAL,
            embed_price_per_1k REAL,
            cost REAL,
            status TEXT NOT NULL,
            error TEXT,
            duration_ms INTEGER,
            conversation_id TEXT,
            turn_id TEXT
        );
        CREATE TABLE usage_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO model_prices(model, prompt_per_1k, completion_per_1k, embed_per_1k, updated_at)
        VALUES ('m', 0.001, 0.002, 0.0005, 't');
        """
    )
    conn.commit()
    conn.close()
    store = UsageStore(db)
    cols = {
        r[1]
        for r in store.conn.execute("PRAGMA table_info(model_prices)").fetchall()
    }
    assert "prompt_per_1m" in cols
    assert "cache_input_per_1m" in cols
    row = store.get_price("m")
    assert row is not None
    assert row["prompt_per_1m"] == 1.0
    assert row["completion_per_1m"] == 2.0
    assert row["embed_per_1m"] == 0.5
    assert store.prefs()["price_unit"] == "per_1m"
    store.close()


def test_usage_unknown_tokens_no_fake_cost(tmp_path):
    store = UsageStore(tmp_path / "usage.db")
    rec = UsageRecorder(store)
    store.upsert_price("m2", prompt_per_1m=1.0, completion_per_1m=1.0)
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
    prices = store.list_prices()
    assert any(p["model"] == "new-model" for p in prices)
    row = next(p for p in prices if p["model"] == "new-model")
    assert row["kinds"] == ["embed"]


def test_model_kinds_separate_chat_and_embed(tmp_path):
    store = UsageStore(tmp_path / "usage.db")
    rec = UsageRecorder(store)
    rec.record(model="chat-m", kind="chat", status="ok")
    rec.record(model="emb-m", kind="embed", status="ok")
    by_model = {p["model"]: p["kinds"] for p in store.list_prices()}
    assert by_model["chat-m"] == ["chat"]
    assert by_model["emb-m"] == ["embed"]


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
