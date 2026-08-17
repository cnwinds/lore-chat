"""一次性：旧媒体根 → 媒体/上传|生成/{年月}；并重写会话附件引用。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from app.engine.conversations import ConversationStore
from app.engine.knowledge_writer import (
    KbPathExistsError,
    KnowledgeWriter,
    suggest_alternate_filename,
)
from app.storage.kb_media_paths import (
    LEGACY_GENERATED_ROOT,
    LEGACY_INBOX_ROOT,
    MEDIA_GENERATED,
    MEDIA_ROOT,
    MEDIA_UPLOADS,
    is_image_filename,
    is_legacy_generated_path,
    is_legacy_inbox_image_path,
    is_year_month_period,
    media_generated_dir,
    media_upload_dir,
    parse_year_only_media_file,
    rewrite_json_media_paths,
    year_month,
)
from app.storage.repo import KnowledgeRepo

logger = logging.getLogger(__name__)

MIGRATION_ID = "media-layout-v2"
MARKER_NAME = f"{MIGRATION_ID}.done"
# 旧标记：有年目录待重分桶时仍会再跑
_LEGACY_MARKER_NAMES = ("media-layout-v1.done",)


def migration_marker_path(kb_root: Path) -> Path:
    return kb_root / ".kb" / "migrations" / MARKER_NAME


def _period_from_mtime(abs_path: Path) -> str:
    ts = abs_path.stat().st_mtime
    return year_month(datetime.fromtimestamp(ts, tz=timezone.utc))


def _unique_filename(directory: str, filename: str, repo: KnowledgeRepo) -> str:
    """与 import 冲突换名一致：stem (n).ext。"""
    candidate = filename
    for _ in range(64):
        if not repo.abs_path(f"{directory}/{candidate}").exists():
            return candidate
        candidate = suggest_alternate_filename(candidate)
    raise RuntimeError(f"无法为 {directory}/{filename} 生成唯一名")


def _move_or_reuse(
    writer: KnowledgeWriter,
    *,
    from_path: str,
    to_directory: str,
    to_filename: str,
) -> str:
    repo = writer.repo
    dest = f"{to_directory}/{to_filename}".replace("//", "/")
    dest_abs = repo.abs_path(dest)
    src_abs = repo.abs_path(from_path)
    if not src_abs.is_file():
        return from_path
    if dest_abs.exists():
        if dest_abs.read_bytes() == src_abs.read_bytes():
            writer.delete_entry(from_path)
            return dest
        to_filename = _unique_filename(to_directory, to_filename, repo)
    try:
        return writer.move_entry(
            from_path=from_path,
            to_directory=to_directory,
            to_filename=to_filename,
        )
    except KbPathExistsError:
        to_filename = _unique_filename(to_directory, to_filename, repo)
        return writer.move_entry(
            from_path=from_path,
            to_directory=to_directory,
            to_filename=to_filename,
        )


def _collect_legacy_moves(repo: KnowledgeRepo) -> list[tuple[str, str, str]]:
    """返回 (from_rel, to_directory, to_filename)。目标目录一律按 mtime 的 {年月}。"""
    moves: list[tuple[str, str, str]] = []
    for rel in repo.list_tree():
        norm = rel.replace("\\", "/").lstrip("/")
        name = PurePosixPath(norm).name
        abs_p = repo.abs_path(norm)
        if is_legacy_generated_path(norm) and norm != LEGACY_GENERATED_ROOT:
            period = _period_from_mtime(abs_p)
            moves.append((norm, media_generated_dir(period), name))
            continue
        if is_legacy_inbox_image_path(norm):
            period = _period_from_mtime(abs_p)
            moves.append((norm, media_upload_dir(period), name))
            continue
        year_only = parse_year_only_media_file(norm)
        if year_only is not None:
            track, _year, fname = year_only
            period = _period_from_mtime(abs_p)
            dest_dir = (
                media_generated_dir(period)
                if track == "generated"
                else media_upload_dir(period)
            )
            dest = f"{dest_dir}/{fname}"
            if dest == norm:
                continue
            moves.append((norm, dest_dir, fname))
    return moves


def infer_path_map_from_media_tree(repo: KnowledgeRepo) -> dict[str, str]:
    """从已迁入的 媒体/ 树反推旧路径映射（中断后补写会话引用）。"""
    path_map: dict[str, str] = {}
    gen_prefix = f"{MEDIA_ROOT}/{MEDIA_GENERATED}/"
    up_prefix = f"{MEDIA_ROOT}/{MEDIA_UPLOADS}/"
    inbox_by_name: dict[str, list[str]] = {}
    for rel in repo.list_tree():
        norm = rel.replace("\\", "/").lstrip("/")
        if norm.startswith(gen_prefix):
            rest = norm[len(gen_prefix) :]
            if not rest:
                continue
            path_map[f"{LEGACY_GENERATED_ROOT}/{rest}"] = norm
            parts = [p for p in rest.split("/") if p]
            # 年月目录：兼映射 generated/{年}/… 与 媒体/生成/{年}/…
            if len(parts) >= 2 and is_year_month_period(parts[0]):
                y = parts[0][:4]
                alias_rest = "/".join([y, *parts[1:]])
                path_map[f"{LEGACY_GENERATED_ROOT}/{alias_rest}"] = norm
                path_map[f"{MEDIA_ROOT}/{MEDIA_GENERATED}/{alias_rest}"] = norm
            continue
        if norm.startswith(up_prefix) and is_image_filename(PurePosixPath(norm).name):
            name = PurePosixPath(norm).name
            inbox_by_name.setdefault(name, []).append(norm)
            rest = norm[len(up_prefix) :]
            parts = [p for p in rest.split("/") if p]
            if len(parts) >= 2 and is_year_month_period(parts[0]):
                y = parts[0][:4]
                path_map[f"{MEDIA_ROOT}/{MEDIA_UPLOADS}/{y}/{name}"] = norm
    for name, dests in inbox_by_name.items():
        dests_sorted = sorted(dests)
        path_map[f"{LEGACY_INBOX_ROOT}/{name}"] = dests_sorted[0]
    return path_map


def rewrite_conversation_media_paths(
    conversations: ConversationStore,
    path_map: dict[str, str],
) -> int:
    """经 ConversationStore 公开 API 重写 attachments / timeline 中的旧路径。"""
    return conversations.transform_message_json_columns(
        lambda raw: rewrite_json_media_paths(raw, path_map)
    )


def rewrite_markdown_generated_links(
    writer: KnowledgeWriter,
    path_map: dict[str, str] | None = None,
) -> int:
    """KB 内 .md：](generated/ → ](媒体/生成/，并替换 path_map 中的旧路径。"""
    old = f"]({LEGACY_GENERATED_ROOT}/"
    new = f"]({MEDIA_ROOT}/{MEDIA_GENERATED}/"
    mapping = path_map or {}
    changed = 0
    for rel in writer.repo.list_tree():
        if not rel.endswith(".md"):
            continue
        try:
            doc = writer.repo.read_doc(rel)
        except Exception:
            continue
        body = doc.body
        # 先按 path_map（含 generated/{年}/… → 年月）替换，再做前缀兜底
        for src, dst in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
            if src in body:
                body = body.replace(src, dst)
        if old in body:
            body = body.replace(old, new)
        if body == doc.body:
            continue
        writer.persist_document(
            rel,
            dict(doc.meta),
            body if body.endswith("\n") else body + "\n",
            commit_msg=f"migrate: media paths in {rel}",
            changelog_line=f"迁移媒体路径 {rel}",
        )
        changed += 1
    return changed


def legacy_media_needs_migration(repo: KnowledgeRepo) -> bool:
    for rel in repo.list_tree():
        norm = rel.replace("\\", "/").lstrip("/")
        if is_legacy_generated_path(norm) and norm != LEGACY_GENERATED_ROOT:
            return True
        if is_legacy_inbox_image_path(norm):
            return True
        if parse_year_only_media_file(norm) is not None:
            return True
    return False


def run_media_layout_migration(
    *,
    knowledge_writer: KnowledgeWriter,
    conversations: ConversationStore,
    force: bool = False,
) -> dict[str, Any]:
    """幂等迁移。

    跳过条件：已有 v2 标记、无残留旧根/年目录、且非 force。
    旧根或 媒体/…/{年}/ 仍在时即使有标记也会再跑；无标记时也会做引用重写。
    """
    repo = knowledge_writer.repo
    kb_root = Path(repo.root)
    marker = migration_marker_path(kb_root)
    needs_files = legacy_media_needs_migration(repo)
    if marker.exists() and not force and not needs_files:
        return {"skipped": True, "reason": "marker_exists"}

    path_map = infer_path_map_from_media_tree(repo)
    moved = 0
    moved_map: dict[str, str] = {}
    for from_path, to_dir, to_name in _collect_legacy_moves(repo):
        if not repo.abs_path(from_path).exists():
            continue
        new_path = _move_or_reuse(
            knowledge_writer,
            from_path=from_path,
            to_directory=to_dir,
            to_filename=to_name,
        )
        moved_map[from_path] = new_path
        moved += 1

    # 搬家后重新推断，并以本轮搬家结果覆盖（含冲突换名）
    path_map = infer_path_map_from_media_tree(repo)
    path_map.update(moved_map)

    conv_updated = rewrite_conversation_media_paths(conversations, path_map)
    md_updated = rewrite_markdown_generated_links(knowledge_writer, path_map)

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "id": MIGRATION_ID,
                "moved": moved,
                "path_map_size": len(path_map),
                "conversation_rows": conv_updated,
                "markdown_files": md_updated,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    # 清理旧 v1 标记，避免并存误导
    for legacy_name in _LEGACY_MARKER_NAMES:
        legacy = kb_root / ".kb" / "migrations" / legacy_name
        if legacy.exists():
            try:
                legacy.unlink()
            except OSError:
                pass
    logger.info(
        "media layout migration done: moved=%s conv_rows=%s md=%s",
        moved,
        conv_updated,
        md_updated,
    )
    return {
        "skipped": False,
        "moved": moved,
        "path_map": path_map,
        "conversation_rows": conv_updated,
        "markdown_files": md_updated,
    }
