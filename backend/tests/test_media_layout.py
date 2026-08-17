"""kb_media_paths 与媒体目录迁移。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.engine.conversations import ConversationStore
from app.engine.knowledge_writer import KnowledgeWriter
from app.storage.kb_media_paths import (
    MEDIA_ROOT,
    is_media_path,
    media_generated_dir,
    media_upload_dir,
    rewrite_legacy_media_path,
    year_month,
)
from app.storage.media_layout_migration import (
    migration_marker_path,
    run_media_layout_migration,
)
from app.storage.repo import KnowledgeRepo


def test_media_path_helpers():
    assert media_upload_dir("2026-08") == "媒体/上传/2026-08"
    assert media_generated_dir("2026-08") == "媒体/生成/2026-08"
    assert is_media_path("媒体/上传/2026-08/a.png")
    assert not is_media_path("未分类/a.png")
    ym = year_month()
    assert rewrite_legacy_media_path("generated/2026/a.png") == f"媒体/生成/{ym}/a.png"
    assert (
        rewrite_legacy_media_path("媒体/生成/2026/a.png") == f"媒体/生成/{ym}/a.png"
    )
    assert (
        year_month(datetime(2026, 8, 17, 1, 0, tzinfo=timezone.utc)) == "2026-08"
    )


def test_media_layout_migration_moves_and_rewrites(tmp_path: Path):
    repo = KnowledgeRepo(tmp_path)
    writer = KnowledgeWriter(repo)
    writer.import_entry(
        directory="generated/2026", filename="a.png", data=b"png-a"
    )
    writer.import_entry(directory="未分类", filename="x.jpg", data=b"jpg-x")
    writer.import_entry(
        directory="未分类", filename="notes.txt", data=b"keep"
    )
    writer.persist_document(
        "doc.md",
        {"title": "t"},
        "见图 ![](generated/2026/a.png)\n",
        commit_msg="test: doc",
        changelog_line="test doc",
    )

    store = ConversationStore(tmp_path / ".kb" / "conversations")
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="图", client_message_id="cli-m", observation_allowed=False
    )
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={
            "text": "ok",
            "timeline": [
                {
                    "type": "tool",
                    "id": "t1",
                    "tool": "generate_image",
                    "status": "done",
                    "summary": "已生成图片 → generated/2026/a.png",
                    "attachments": ["generated/2026/a.png"],
                }
            ],
            "attachments": ["generated/2026/a.png", "未分类/x.jpg"],
            "sources": [],
            "status": "complete",
        },
    )

    result = run_media_layout_migration(
        knowledge_writer=writer, conversations=store
    )
    assert result["skipped"] is False
    assert result["moved"] == 2
    ym = year_month()
    assert (tmp_path / "媒体" / "生成" / ym / "a.png").is_file()
    assert not (tmp_path / "generated" / "2026" / "a.png").exists()
    assert not (tmp_path / "媒体" / "生成" / "2026" / "a.png").exists()
    upload_hits = list((tmp_path / "媒体" / "上传").rglob("x.jpg"))
    assert len(upload_hits) == 1
    assert upload_hits[0].parent.name == ym
    assert (tmp_path / "未分类" / "notes.txt").is_file()
    assert not (tmp_path / "未分类" / "x.jpg").exists()

    gen_rel = f"媒体/生成/{ym}/a.png"
    assistant = store.get(cid)["messages"][1]
    assert assistant["attachments"] == [
        gen_rel,
        str(upload_hits[0].relative_to(tmp_path).as_posix()),
    ]
    assert assistant["timeline"][0]["attachments"] == [gen_rel]
    assert gen_rel in assistant["timeline"][0]["summary"]

    body = (tmp_path / "doc.md").read_text(encoding="utf-8")
    assert "generated/2026/a.png" not in body
    assert gen_rel in body

    marker = migration_marker_path(tmp_path)
    assert marker.is_file()

    again = run_media_layout_migration(
        knowledge_writer=writer, conversations=store
    )
    assert again["skipped"] is True
    assert json.loads(marker.read_text(encoding="utf-8"))["id"] == "media-layout-v2"
    assert MEDIA_ROOT == "媒体"


def test_media_layout_migration_rebuckets_year_dirs(tmp_path: Path):
    """存量 媒体/…/{年}/ 按 mtime 重分桶到 {年月}，并改写会话引用。"""
    repo = KnowledgeRepo(tmp_path)
    writer = KnowledgeWriter(repo)
    writer.import_entry(
        directory="媒体/生成/2026", filename="a.png", data=b"png-a"
    )
    writer.import_entry(
        directory="媒体/上传/2026", filename="x.jpg", data=b"jpg-x"
    )

    store = ConversationStore(tmp_path / ".kb" / "conversations")
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="图", client_message_id="cli-year", observation_allowed=False
    )
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={
            "text": "ok",
            "timeline": [],
            "attachments": ["媒体/生成/2026/a.png", "媒体/上传/2026/x.jpg"],
            "sources": [],
            "status": "complete",
        },
    )

    result = run_media_layout_migration(
        knowledge_writer=writer, conversations=store
    )
    assert result["skipped"] is False
    assert result["moved"] == 2
    ym = year_month()
    assert (tmp_path / "媒体" / "生成" / ym / "a.png").is_file()
    assert (tmp_path / "媒体" / "上传" / ym / "x.jpg").is_file()
    assert not (tmp_path / "媒体" / "生成" / "2026" / "a.png").exists()
    assistant = store.get(cid)["messages"][1]
    assert assistant["attachments"] == [
        f"媒体/生成/{ym}/a.png",
        f"媒体/上传/{ym}/x.jpg",
    ]


def test_media_layout_migration_recovers_refs_after_interrupt(tmp_path: Path):
    """文件已在年月目录、无标记、会话仍写旧路径 → 重跑应推断 path_map 并改写。"""
    repo = KnowledgeRepo(tmp_path)
    writer = KnowledgeWriter(repo)
    ym = year_month()
    writer.import_entry(
        directory=f"媒体/生成/{ym}", filename="a.png", data=b"png-a"
    )
    writer.import_entry(
        directory=f"媒体/上传/{ym}", filename="x.jpg", data=b"jpg-x"
    )

    store = ConversationStore(tmp_path / ".kb" / "conversations")
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="图", client_message_id="cli-int", observation_allowed=False
    )
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={
            "text": "ok",
            "timeline": [],
            "attachments": ["generated/2026/a.png", "未分类/x.jpg"],
            "sources": [],
            "status": "complete",
        },
    )

    assert not migration_marker_path(tmp_path).exists()
    result = run_media_layout_migration(
        knowledge_writer=writer, conversations=store
    )
    assert result["skipped"] is False
    assert result["moved"] == 0
    assert result["conversation_rows"] >= 1
    assistant = store.get(cid)["messages"][1]
    assert assistant["attachments"] == [
        f"媒体/生成/{ym}/a.png",
        f"媒体/上传/{ym}/x.jpg",
    ]
    assert migration_marker_path(tmp_path).is_file()


def test_media_layout_reruns_when_legacy_reappears(tmp_path: Path):
    repo = KnowledgeRepo(tmp_path)
    writer = KnowledgeWriter(repo)
    store = ConversationStore(tmp_path / ".kb" / "conversations")
    first = run_media_layout_migration(
        knowledge_writer=writer, conversations=store
    )
    assert first["skipped"] is False
    assert migration_marker_path(tmp_path).is_file()

    writer.import_entry(
        directory="generated/2026", filename="b.png", data=b"png-b"
    )
    second = run_media_layout_migration(
        knowledge_writer=writer, conversations=store
    )
    assert second["skipped"] is False
    assert second["moved"] == 1
    ym = year_month()
    assert (tmp_path / "媒体" / "生成" / ym / "b.png").is_file()


def test_admin_migrate_media_layout_endpoint(client):
    r = client.post("/api/admin/migrate-media-layout")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert "moved" in body
    r2 = client.post("/api/admin/migrate-media-layout")
    assert r2.status_code == 200, r2.text
    assert r2.json()["skipped"] is True
