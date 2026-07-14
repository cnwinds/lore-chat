from app.engine.workspace import ensure_workspace_id


def test_ensure_workspace_id_stable(tmp_path):
    a = ensure_workspace_id(tmp_path)
    b = ensure_workspace_id(tmp_path)
    assert a == b
    assert len(a) >= 8
    data = (tmp_path / ".kb" / "workspace.json").read_text(encoding="utf-8")
    assert a in data
