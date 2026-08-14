import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.backup.export_kb import build_directory_zip, build_export_zip
from app.config import Settings
from app.main import create_app
from app.models.llm import FakeLLMClient


def test_export_includes_docs_and_index(tmp_path: Path):
    kb = tmp_path / "kb"
    (kb / "技术").mkdir(parents=True)
    (kb / "技术" / "a.md").write_text("# hi\n", encoding="utf-8")
    (kb / "manifest.json").write_text('{"format_version": 0}\n', encoding="utf-8")
    idx = kb / ".kb" / "index"
    (idx / "vec").mkdir(parents=True)
    (idx / "vec" / "dummy.bin").write_bytes(b"x")
    (idx / "fts.db").write_bytes(b"sqlite")
    (idx / "conversation_fts.db").write_bytes(b"sqlite")
    (idx / "fts.db-wal").write_bytes(b"wal")
    (idx / "fts.db-shm").write_bytes(b"shm")
    (kb / ".kb" / "auth.json").write_text('{"password_hash":"x"}', encoding="utf-8")

    out = tmp_path / "out.zip"
    build_export_zip(kb, out)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    norm = [n.replace("\\", "/") for n in names]
    assert any(n.endswith("技术/a.md") for n in norm)
    assert any("auth.json" in n for n in norm)
    assert any(n.endswith("manifest.json") for n in norm)
    assert names.count("manifest.json") == 1
    assert any(n.endswith(".kb/index/fts.db") for n in norm)
    assert any(n.endswith(".kb/index/conversation_fts.db") for n in norm)
    assert any(".kb/index/vec/dummy.bin" in n for n in norm)
    assert not any(n.endswith(".db-wal") or n.endswith(".db-shm") for n in norm)


def test_directory_zip_contains_folder_prefix(tmp_path: Path):
    kb = tmp_path / "kb"
    (kb / "导入测试").mkdir(parents=True)
    (kb / "导入测试" / "a.md").write_text("# a\n", encoding="utf-8")
    (kb / "导入测试" / "子").mkdir()
    (kb / "导入测试" / "子" / "b.txt").write_bytes(b"hi")

    out = tmp_path / "pack.zip"
    name = build_directory_zip(kb, "导入测试", out)
    assert name == "导入测试"
    with zipfile.ZipFile(out) as z:
        names = sorted(z.namelist())
    assert names == ["导入测试/a.md", "导入测试/子/b.txt"]


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
