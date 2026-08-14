from pathlib import Path

from fastapi.testclient import TestClient

from app.backup.export_kb import build_export_zip
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


def test_reindex_after_import_restores_doc_search(client, tmp_path):
    pack = _make_pack(
        tmp_path,
        "技术/searchme.md",
        "unique-reindex-token-xyz content for search\n",
    )
    with open(pack, "rb") as f:
        r = client.post(
            "/api/admin/import",
            files={"file": ("pack.zip", f, "application/zip")},
            data={"mode": "empty_only"},
        )
    assert r.status_code == 200, r.text

    # Import remounts KB and wipes auth; re-establish session.
    r = client.post("/api/auth/setup", json={"password": "test-password-123"})
    assert r.status_code == 200, r.text

    container = client.app.state.container
    assert container.indexer.fulltext.query("unique-reindex-token-xyz") == []

    r = client.post("/api/admin/reindex")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["docs_indexed"] >= 1

    hits = container.indexer.fulltext.query("unique-reindex-token-xyz")
    assert hits


def test_reindex_api_requires_auth(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge")
    app = create_app(settings=settings, llm=FakeLLMClient(embed_dim=8))
    with TestClient(app) as c:
        r = c.post("/api/admin/reindex")
        assert r.status_code == 401


def test_reindex_blocked_during_maintenance(client):
    client.app.state.maintenance_lock.acquire("export")
    try:
        r = client.post("/api/admin/reindex")
        assert r.status_code == 503
        assert r.json()["code"] == "maintenance"
    finally:
        client.app.state.maintenance_lock.release()


def test_reindex_skips_binary_assets_and_backfills_conversations(client):
    """导入后常见：KB 含图片；重建索引不得因 UTF-8 失败而跳过会话回填。"""
    container = client.app.state.container
    container.repo.write_doc(
        "技术/note.md",
        {"title": "笔记"},
        "markdown body for docs\n",
        commit_msg="seed md",
    )
    # JPEG SOI — 非 UTF-8，旧逻辑会在 read_doc 处崩溃
    container.repo.write_bytes(
        "媒体/上传/fixture.jpg",
        b"\xff\xd8\xff\xe0" + b"\x00" * 64,
        commit_msg="seed binary",
    )
    cid = container.conversations.create(title="历史会话")
    token = "unique-conv-reindex-token-zyx"
    container.conversations.begin_turn(
        cid, token, "cli-reindex-1", observation_allowed=False
    )

    r = client.post("/api/admin/reindex")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["docs_indexed"] >= 1
    assert body["conversations_fts"] >= 1

    hits = container.conversation_fts.query(token, k=5)
    assert hits
    assert any(h.conversation_id == cid for h in hits)
