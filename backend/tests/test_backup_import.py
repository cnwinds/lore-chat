import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.admin_routes import _import_failure_http
from app.backup.empty import is_kb_empty
from app.backup.export_kb import build_export_zip
from app.backup.import_kb import ImportResult, backup_dir_for, import_kb
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


def _inject_zip_sessions(pack: Path, sessions: dict) -> None:
    with zipfile.ZipFile(pack, "a") as zf:
        zf.writestr(".kb/sessions.json", json.dumps(sessions))


def test_import_empty_only_rejects_non_empty(tmp_path: Path):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "技术").mkdir()
    (kb / "技术" / "a.md").write_text("# a\n", encoding="utf-8")
    pack = _make_pack(tmp_path, "技术/b.md", "# b\n")

    result = import_kb(kb, pack, "empty_only")
    assert result.ok is False
    assert result.code == "kb_not_empty"
    assert result.message == "knowledge base is not empty"
    assert (kb / "技术" / "a.md").is_file()
    assert not (kb / "技术" / "b.md").exists()


def test_import_missing_manifest_sets_code(tmp_path: Path):
    kb = tmp_path / "kb"
    kb.mkdir()
    pack = tmp_path / "bad.zip"
    with zipfile.ZipFile(pack, "w") as zf:
        zf.writestr("技术/a.md", "# a\n")

    result = import_kb(kb, pack, "empty_only")
    assert result.ok is False
    assert result.code == "invalid_manifest"
    assert result.message == "missing manifest.json"


def test_import_unsupported_format_sets_code(tmp_path: Path):
    kb = tmp_path / "kb"
    kb.mkdir()
    pack = tmp_path / "bad.zip"
    with zipfile.ZipFile(pack, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format_version": 99}))

    result = import_kb(kb, pack, "empty_only")
    assert result.ok is False
    assert result.code == "unsupported_format"
    assert "format_version" in result.message


def test_import_failure_http_maps_code_not_message():
    result = ImportResult(
        ok=False,
        backup_path=None,
        message="missing manifest.json",
        code="import_failed",
    )
    exc = _import_failure_http(result)
    assert exc.status_code == 400
    assert exc.detail["code"] == "import_failed"
    assert exc.detail["detail"] == "missing manifest.json"


def test_import_failure_http_invalid_manifest_is_422():
    result = ImportResult(
        ok=False,
        backup_path=None,
        message="missing manifest.json",
        code="invalid_manifest",
    )
    exc = _import_failure_http(result)
    assert exc.status_code == 422
    assert exc.detail["code"] == "invalid_manifest"


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


def test_import_empty_only_survives_promote_failure(tmp_path: Path, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    pack = _make_pack(tmp_path, "技术/a.md", "# hi\n")

    import app.backup.import_kb as import_mod

    def fail_promote(staging: Path, kb_path: Path) -> None:
        raise OSError("simulated promote failure")

    monkeypatch.setattr(import_mod, "_promote_staging", fail_promote)

    result = import_kb(kb, pack, "empty_only")
    assert result.ok is False
    assert result.code == "import_failed"
    assert "simulated promote failure" in result.message
    assert is_kb_empty(kb)


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
    assert result.code == "import_failed"
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
    tree = client.get("/api/tree")
    assert tree.status_code == 200, tree.text


def test_import_api_keeps_importer_cookie_when_pack_has_other_sessions(
    client, tmp_path
):
    pack = _make_pack(tmp_path, "技术/imported.md", "# imported\n")
    packed_exp = "2099-01-01T00:00:00+00:00"
    _inject_zip_sessions(pack, {"packed-sid": {"expires_at": packed_exp}})
    with open(pack, "rb") as f:
        r = client.post(
            "/api/admin/import",
            files={"file": ("pack.zip", f, "application/zip")},
            data={"mode": "empty_only"},
        )
    assert r.status_code == 200, r.text
    assert client.get("/api/tree").status_code == 200
    kb = client.app.state.settings_store.get().kb_path
    sessions = json.loads((kb / ".kb" / "sessions.json").read_text(encoding="utf-8"))
    assert sessions["packed-sid"]["expires_at"] == packed_exp
    cookie = client.cookies.get("lorechat_session")
    assert cookie
    assert cookie in sessions


def test_import_api_overwrite_with_open_chroma(client, tmp_path):
    kb = client.app.state.settings_store.get().kb_path
    (kb / "技术").mkdir(parents=True)
    (kb / "技术" / "keep.md").write_text("# keep\n", encoding="utf-8")
    client.app.state.container.indexer.vector._chroma.collection()
    client.app.state.container.conversation_vector._chroma.collection()
    pack = _make_pack(tmp_path, "new/y.md", "new\n")
    with open(pack, "rb") as f:
        r = client.post(
            "/api/admin/import",
            files={"file": ("pack.zip", f, "application/zip")},
            data={"mode": "overwrite"},
        )
    assert r.status_code == 200, r.text
    assert (kb / "new" / "y.md").read_text(encoding="utf-8") == "new\n"
    assert not (kb / "技术" / "keep.md").exists()
    assert client.get("/api/tree").status_code == 200


def test_import_api_failure_includes_backup_path(client, tmp_path, monkeypatch):
    kb = client.app.state.settings_store.get().kb_path
    (kb / "技术").mkdir(parents=True)
    (kb / "技术" / "keep.md").write_text("# keep\n", encoding="utf-8")
    pack = _make_pack(tmp_path, "new/y.md", "new\n")

    import app.backup.import_kb as import_mod

    def fail_promote(staging: Path, kb_path: Path) -> None:
        raise OSError("simulated promote failure")

    monkeypatch.setattr(import_mod, "_promote_staging", fail_promote)

    with open(pack, "rb") as f:
        r = client.post(
            "/api/admin/import",
            files={"file": ("pack.zip", f, "application/zip")},
            data={"mode": "overwrite"},
        )
    assert r.status_code == 400, r.text
    body = r.json()["detail"]
    assert body["code"] == "import_failed"
    assert "rolled back" in body["detail"]
    assert "backup_path" in body
    assert Path(body["backup_path"]).is_file()
    assert (kb / "技术" / "keep.md").read_text(encoding="utf-8") == "# keep\n"


def test_import_api_invalid_manifest(client, tmp_path):
    pack = tmp_path / "bad.zip"
    with zipfile.ZipFile(pack, "w") as zf:
        zf.writestr("技术/a.md", "# a\n")
    with open(pack, "rb") as f:
        r = client.post(
            "/api/admin/import",
            files={"file": ("pack.zip", f, "application/zip")},
            data={"mode": "empty_only"},
        )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "invalid_manifest"
    assert detail["detail"] == "missing manifest.json"


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
    detail = r.json()["detail"]
    assert detail["code"] == "kb_not_empty"
    assert detail["detail"] == "knowledge base is not empty"


def test_write_routes_blocked_during_maintenance(client, tmp_path):
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
            "/api/kb/import",
            files={"file": ("x.txt", io.BytesIO(b"hi"), "text/plain")},
            data={"directory": "未分类"},
        )
        assert r.status_code == 503

        r = client.get("/api/admin/export")
        assert r.status_code == 503

        pack = _make_pack(tmp_path, "技术/blocked.md", "# blocked\n")
        with open(pack, "rb") as f:
            r = client.post(
                "/api/admin/import",
                files={"file": ("pack.zip", f, "application/zip")},
                data={"mode": "empty_only"},
            )
        assert r.status_code == 503
        assert r.json()["code"] == "maintenance"

        r = client.post("/api/admin/reindex")
        assert r.status_code == 503
        assert r.json()["code"] == "maintenance"
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
