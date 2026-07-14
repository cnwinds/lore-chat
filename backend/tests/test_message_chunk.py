from app.index.message_chunk import chunk_message, coverage_ok


def test_chunk_covers_all_codepoints():
    text = "甲" * 50 + "\n\n" + "乙" * 50
    chunks = chunk_message(text, size=40, overlap=10)
    assert chunks
    assert coverage_ok(text, chunks)


def test_chunk_preserves_offsets_after_masking():
    from app.engine.secrets import mask_secrets

    raw = "before sk-abcdefghijklmnopqrstuvwxyz012345 after"
    masked, _ = mask_secrets(raw)
    chunks = chunk_message(masked, size=20, overlap=5)
    assert coverage_ok(masked, chunks)
    assert len(list(raw)) == len(list(masked))
