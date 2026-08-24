"""分享快照物化单元测试。"""

from __future__ import annotations

from app.engine.share_snapshot import build_public_conversation_payload


def test_conversation_share_materializes_file_attachment(tmp_path):
    kb = tmp_path / "knowledge"
    attach = kb / "附件" / "spec.pdf"
    attach.parent.mkdir(parents=True, exist_ok=True)
    attach.write_bytes(b"%PDF-1.4 share attachment")

    snapshot = {
        "messages": [
            {
                "id": "u1",
                "role": "user",
                "text": "见附件",
                "ts": "2026-08-24T10:00:00",
                "status": "complete",
                "attachments": ["附件/spec.pdf"],
            }
        ]
    }
    payload = build_public_conversation_payload(
        snapshot,
        title="t",
        exp_iso=None,
        kb_path=kb,
        public_base_url="https://share.example.com",
        grant_ttl_sec=3600,
    )
    att = payload["messages"][0]["attachments"][0]
    assert att.startswith("https://share.example.com/api/media/grant/")


def test_media_grant_serves_non_image_file(client, tmp_path):
    kb = tmp_path / "knowledge"
    attach = kb / "附件" / "spec.pdf"
    attach.parent.mkdir(parents=True, exist_ok=True)
    attach.write_bytes(b"%PDF-1.4 grant")

    from app.models.media_grants import MediaGrantStore

    grant_id = MediaGrantStore(kb).issue("附件/spec.pdf", ttl_sec=3600)
    resp = client.get(f"/api/media/grant/{grant_id}")
    assert resp.status_code == 200, resp.text
    assert resp.content.startswith(b"%PDF")
