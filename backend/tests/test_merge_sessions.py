from app.engine.merge_sessions import MergeSessionStore


def test_create_and_get_pending(tmp_path):
    store = MergeSessionStore(tmp_path / "merge_sessions.json")
    sid = store.create(
        new_path="a/merged.md",
        source_paths=["a/1.md", "a/2.md"],
        instruction="保留表格",
        order=["a/1.md", "a/2.md"],
        generated_content_hash="sha256:abc",
    )
    s = store.get(sid)
    assert s["status"] == "pending_review"
    assert s["new_path"] == "a/merged.md"


def test_find_active_by_path(tmp_path):
    store = MergeSessionStore(tmp_path / "merge_sessions.json")
    sid = store.create(
        new_path="x.md", source_paths=["a.md", "b.md"],
        instruction="", order=["a.md", "b.md"], generated_content_hash="h",
    )
    found = store.find_active_by_path("x.md")
    assert found is not None
    assert found["id"] == sid


def test_user_modified(tmp_path):
    from app.engine.content_hash import body_hash
    store = MergeSessionStore(tmp_path / "merge_sessions.json")
    h = body_hash("content")
    sid = store.create(
        new_path="x.md", source_paths=["a.md", "b.md"],
        instruction="", order=["a.md", "b.md"], generated_content_hash=h,
    )
    assert store.user_modified(sid, "content") is False
    assert store.user_modified(sid, "changed") is True
