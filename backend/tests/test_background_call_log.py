
from app.engine.background.call_log import BackgroundCallLog


def test_call_log_record_trim_and_delete(tmp_path):
    db = tmp_path / "bg.db"
    log = BackgroundCallLog(db)
    long_resp = "x" * 20000
    log.record(
        purpose="memory.owner_extract",
        variant=None,
        model="m",
        model_label="L",
        candidate_id="c1",
        chain="utility",
        temperature=0.1,
        api_messages=[{"role": "system", "content": "sys"}],
        response=long_resp,
        status="ok",
        error=None,
        duration_ms=10,
        prompt_tokens=1,
        completion_tokens=2,
        conversation_id="conv-1",
        scope=None,
    )
    rows = log.list_calls("memory.owner_extract", limit=5)
    assert len(rows) == 1
    detail = log.get_call(rows[0]["id"])
    assert detail is not None
    assert detail["response_truncated"] is True
    assert len(detail["response"] or "") <= 16000

    for i in range(35):
        log.record(
            purpose="memory.owner_extract",
            variant=None,
            model="m",
            model_label="L",
            candidate_id="c1",
            chain="utility",
            temperature=0.1,
            api_messages=[{"role": "user", "content": str(i)}],
            response="ok",
            status="ok",
            error=None,
            duration_ms=1,
            prompt_tokens=1,
            completion_tokens=1,
            conversation_id=None,
            scope=None,
        )
    assert len(log.list_calls("memory.owner_extract", limit=50)) == 30

    log.delete_conversation("conv-1")
    log.delete_scope("role:x")
    log.close()


def test_call_log_swallows_bad_blob(tmp_path, monkeypatch):
    log = BackgroundCallLog(tmp_path / "bg2.db")
    log.record(
        purpose="cards.extract",
        variant="dm",
        model=None,
        model_label=None,
        candidate_id=None,
        chain="utility",
        temperature=0.1,
        api_messages=[{"role": "user", "content": "hi"}],
        response="",
        status="ok",
        error=None,
        duration_ms=1,
        prompt_tokens=None,
        completion_tokens=None,
        conversation_id=None,
        scope=None,
    )
    with log._lock:
        log.conn.execute(
            "UPDATE background_calls SET messages_blob = ? WHERE id = 1",
            (b"not-zlib",),
        )
        log.conn.commit()
    assert log.get_call(1) is not None
    log.close()
