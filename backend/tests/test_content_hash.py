from app.engine.content_hash import body_hash, is_body_modified


def test_body_hash_stable_for_same_content():
    h1 = body_hash("hello\n")
    h2 = body_hash("hello")
    assert h1 == h2


def test_is_body_modified_detects_change():
    original = body_hash("alpha")
    assert is_body_modified("beta", original) is True
    assert is_body_modified("alpha\n", original) is False
