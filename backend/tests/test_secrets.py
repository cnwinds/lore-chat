from app.engine.secrets import mask_secrets, scan_secrets


def test_mask_openai_key_preserves_codepoint_length():
    text = "key=sk-abcdefghijklmnopqrstuvwxyz012345"
    masked, spans = mask_secrets(text)
    assert len(list(masked)) == len(list(text))
    assert spans
    assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in masked
    assert "•" in masked


def test_scan_finds_github_pat():
    text = "token ghp_abcdefghijklmnopqrstuvwx1234567890ABCD"
    spans = scan_secrets(text)
    assert spans
