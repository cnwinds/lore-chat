from app.engine.source_key import extend_sources, source_dedupe_key


def test_conversation_key_includes_message_and_range():
    a = {
        "type": "conversation",
        "cid": "c1",
        "message_id": "m1",
        "start_char": 0,
        "end_char": 4,
    }
    b = {**a, "start_char": 4, "end_char": 8}
    assert source_dedupe_key(a) != source_dedupe_key(b)
    assert source_dedupe_key(a) == source_dedupe_key(dict(a))


def test_extend_sources_dedupes_by_key():
    src = {"type": "conversation", "cid": "c1", "message_id": "m1", "start_char": 0, "end_char": 3}
    all_sources: list[dict] = [dict(src)]
    extend_sources(all_sources, [dict(src), {**src, "excerpt": "other"}])
    assert len(all_sources) == 1
