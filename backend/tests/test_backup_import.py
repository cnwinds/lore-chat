import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.backup.export_kb import build_export_zip
from app.backup.import_kb import backup_dir_for, import_kb
from app.config import Settings
from app.main import create_app
from app.models.llm import FakeLLMClient


def _make_pack(tmp_path: Path, rel: str, body: str) -> Path:
    source = tmp_path / "source"
    folder = source / Path(rel).parent
    folder.mkdir(parents=True, exist_ok=True)
    (source / rel).write_text(body, encoding="utf-8")
    out = tmp_path / "pack.zip"
    build_export_zip(source, out)
    return out


def test_import_empty_only_rejects_non_empty(tmp_path: Path):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "技术").mkdir()
    (kb / "技术" / "a.md").write_text("# a\n", encoding="utf-8")
    pack = _make_pack(tmp_path, "技术/b.md", "# b\n")

    result = import_kb(kb, pack, "empty_only")
    assert result.ok is False
    assert result.message == "knowledge base is not empty"
    assert (kb / "技术" / "a.md").is_file()
    assert not (kb / "技术" / "b.md").exists()


def test_import_empty_only_ok(tmp_path: Path):
    kb = tmp_path / "kb"
    kb.mkdir()
    pack = _make_pack(tmp_path, "技术/a.md", "# hi\n")

    result = import_kb(kb, pack, "empty_only")
    assert result.ok is True
    assert (kb / "技术" / "a.md").read_text(encoding="utf-8") == "# hi\n"


def test_overwrite_creates_backup_and_replaces(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BACKUP_DIR", raising=False)
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "old").mkdir()
    (kb / "old" / "x.md").write_text("old\n", encoding="utf-8")
    pack = _make_pack(tmp_path, "new/y.md", "new\n")

    result = import_kb(kb, pack, "overwrite")
    assert result.ok is True
    assert result.backup_path is not None
    assert result.backup_path.is_file()
    assert backup_dir_for(kb) == tmp_path / "lorechat-backups"
    assert not (kb / "old" / "x.md").exists()
    assert (kb / "new" / "y.md").read_text(encoding="utf-8") == "new\n"


def test_overwrite_rollback_on_bad_zip(tmp_path: Path, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "技术").mkdir()
    (kb / "技术" / "a.md").write_text("# keep\n", encoding="utf-8")

    pack = _make_pack(tmp_path, "new/y.md", "new\n")
    calls: list[int] = []

    import app.backup.import_kb as import_mod

    real_promote = import_mod._promote_staging

    def flaky_promote(staging: Path, kb_path: Path) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise OSError("simulated promote failure")
        return real_promote(staging, kb_path)

    monkeypatch.setattr(import_mod, "_promote_staging", flaky_promote)

    result = import_kb(kb, pack, "overwrite")
    assert result.ok is False
    assert "rolled back" in result.message
    assert (kb / "技术" / "a.md").read_text(encoding="utf-8") == "# keep\n"
    assert not (kb / "new" / "y.md").exists()


def test_backup_dir_for_env_override(tmp_path: Path, monkeypatch):
    kb = tmp_path / "kb"
    custom = tmp_path / "custom-backups"
    monkeypatch.setenv("BACKUP_DIR", str(custom))
    assert backup_dir_for(kb) == custom


def test_import_api_empty_only(client, tmp_path):
    pack = _make_pack(tmp_path, "技术/imported.md", "# imported\n")
    with open(pack, "rb") as f:
        r = client.post(
            "/api/admin/import",
            files={"file": ("pack.zip", f, "application/zip")},
            data={"mode": "empty_only"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    kb = client.app.state.settings_store.get().kb_path
    assert (kb / "技术" / "imported.md").is_file()


def test_import_api_rejects_non_empty(client, tmp_path):
    kb = client.app.state.settings_store.get().kb_path
    (kb / "技术").mkdir(parents=True)
    (kb / "技术" / "existing.md").write_text("# x\n", encoding="utf-8")
    pack = _make_pack(tmp_path, "技术/new.md", "# new\n")
    with open(pack, "rb") as f:
        r = client.post(
            "/api/admin/import",
            files={"file": ("pack.zip", f, "application/zip")},
            data={"mode": "empty_only"},
        )
    assert r.status_code == 409


def test_write_routes_blocked_during_maintenance(client):
    client.app.state.maintenance_lock.acquire("export")
    try:
        r = client.post("/api/chat", json={"text": "hi"})
        assert r.status_code == 503
        assert r.json()["code"] == "maintenance"

        r = client.post("/api/ingest", json={"text": "x"})
        assert r.status_code == 503
        assert r.json()["code"] == "maintenance"

        r = client.put("/api/doc", json={"path": "a.md", "body": "b"})
        assert r.status_code == 503

        r = client.post(
            "/api/upload",
            files={"file": ("x.txt", io.BytesIO(b"hi"), "text/plain")},
            data={"category": "未分类"},
        )
        assert r.status_code == 503

        r = client.get("/api/admin/export")
        assert r.status_code == 503
    finally:
        client.app.state.maintenance_lock.release()


def test_read_routes_allowed_during_maintenance(client):
    client.app.state.maintenance_lock.acquire("export")
    try:
        r = client.get("/api/tree")
        assert r.status_code == 200
    finally:
        client.app.state.maintenance_lock.release()


def test_export_requires_auth(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge")
    app = create_app(settings=settings, llm=FakeLLMClient(embed_dim=8))
    with TestClient(app) as c:
        r = c.get("/api/admin/export")
        assert r.status_code == 401
