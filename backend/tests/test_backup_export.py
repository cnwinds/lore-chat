import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.backup.export_kb import build_export_zip
from app.config import Settings
from app.main import create_app
from app.models.llm import FakeLLMClient


def test_export_includes_docs_excludes_index(tmp_path: Path):
    kb = tmp_path / "kb"
    (kb / "技术").mkdir(parents=True)
    (kb / "技术" / "a.md").write_text("# hi\n", encoding="utf-8")
    idx = kb / ".kb" / "index"
    (idx / "vec").mkdir(parents=True)
    (idx / "vec" / "dummy.bin").write_bytes(b"x")
    (idx / "fts.db").write_bytes(b"sqlite")
    (kb / ".kb" / "auth.json").write_text('{"password_hash":"x"}', encoding="utf-8")

    out = tmp_path / "out.zip"
    build_export_zip(kb, out)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    assert any(n.endswith("技术/a.md") or n.endswith("技术\\a.md") for n in names)
    assert any("auth.json" in n for n in names)
    assert any(n.endswith("manifest.json") for n in names)
    assert not any("fts.db" in n for n in names)
    assert not any(
        "/vec/" in n.replace("\\", "/") or n.replace("\\", "/").endswith("/vec")
        for n in names
        if "vec" in n
    )


def test_export_api_requires_auth_and_returns_zip(client, tmp_path):
    kb = client.app.state.settings_store.get().kb_path
    (kb / "技术").mkdir(parents=True)
    (kb / "技术" / "a.md").write_text("# hi\n", encoding="utf-8")

    r = client.get("/api/admin/export")
    assert r.status_code == 200
    assert "zip" in r.headers.get("content-type", "")


def test_export_api_requires_auth(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge")
    app = create_app(settings=settings, llm=FakeLLMClient(embed_dim=8))
    with TestClient(app) as c:
        r = c.get("/api/admin/export")
        assert r.status_code == 401
