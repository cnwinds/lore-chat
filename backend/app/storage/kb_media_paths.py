"""聊天媒体落盘路径约定（上传图 / 生图），前后端常量应对齐。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any
from zoneinfo import ZoneInfo

MEDIA_ROOT = "媒体"
MEDIA_UPLOADS = "上传"
MEDIA_GENERATED = "生成"

# 与产品展示时区一致（上传/生成子目录 {年月}）
_MEDIA_TZ = ZoneInfo("Asia/Shanghai")

# 历史根（迁移源）
LEGACY_GENERATED_ROOT = "generated"
LEGACY_INBOX_ROOT = "未分类"

_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
    ".tif",
    ".tiff",
    ".ico",
}

_YEAR_ONLY_RE = re.compile(r"^\d{4}$")
_YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def year_month(now: datetime | None = None) -> str:
    """媒体子目录用的 {年月}：北京时间 YYYY-MM。"""
    dt = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_MEDIA_TZ).strftime("%Y-%m")


def is_year_only_period(period: str) -> bool:
    return bool(_YEAR_ONLY_RE.match((period or "").strip()))


def is_year_month_period(period: str) -> bool:
    return bool(_YEAR_MONTH_RE.match((period or "").strip()))


def media_upload_dir(period: str | None = None) -> str:
    """聊天上传媒体：媒体/上传/{年月}。"""
    p = (period or year_month()).strip()
    return f"{MEDIA_ROOT}/{MEDIA_UPLOADS}/{p}"


def media_generated_dir(period: str | None = None) -> str:
    """生图 / SVG 等生成媒体：媒体/生成/{年月}。"""
    p = (period or year_month()).strip()
    return f"{MEDIA_ROOT}/{MEDIA_GENERATED}/{p}"


def is_media_path(rel: str) -> bool:
    norm = (rel or "").replace("\\", "/").lstrip("/")
    return norm == MEDIA_ROOT or norm.startswith(f"{MEDIA_ROOT}/")


def is_legacy_generated_path(rel: str) -> bool:
    norm = (rel or "").replace("\\", "/").lstrip("/")
    return norm == LEGACY_GENERATED_ROOT or norm.startswith(
        f"{LEGACY_GENERATED_ROOT}/"
    )


def is_legacy_inbox_image_path(rel: str) -> bool:
    """未分类下直接子级图片路径。"""
    norm = (rel or "").replace("\\", "/").lstrip("/")
    parent = PurePosixPath(norm).parent.as_posix()
    name = PurePosixPath(norm).name
    return parent == LEGACY_INBOX_ROOT and is_image_filename(name)


def parse_year_only_media_file(rel: str) -> tuple[str, str, str] | None:
    """若路径为 媒体/{上传|生成}/{YYYY}/… 下的文件，返回 (track, year, filename)。

    track 为 ``upload`` 或 ``generated``。
    """
    norm = (rel or "").replace("\\", "/").lstrip("/")
    for track, mid in (("generated", MEDIA_GENERATED), ("upload", MEDIA_UPLOADS)):
        prefix = f"{MEDIA_ROOT}/{mid}/"
        if not norm.startswith(prefix):
            continue
        rest = norm[len(prefix) :]
        parts = [p for p in rest.split("/") if p]
        if len(parts) < 2 or not is_year_only_period(parts[0]):
            continue
        return track, parts[0], PurePosixPath(norm).name
    return None


def is_image_filename(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in _IMAGE_SUFFIXES


def rewrite_legacy_media_path(
    rel: str,
    *,
    path_map: dict[str, str] | None = None,
) -> str:
    """将已知旧媒体前缀改写为新媒体路径（无法识别则原样返回）。"""
    norm = (rel or "").replace("\\", "/").lstrip("/")
    mapping = path_map or {}
    if norm in mapping:
        return mapping[norm]
    if is_legacy_generated_path(norm):
        rest = norm[len(LEGACY_GENERATED_ROOT) :].lstrip("/")
        if not rest:
            return f"{MEDIA_ROOT}/{MEDIA_GENERATED}"
        parts = [p for p in rest.split("/") if p]
        # generated/{YYYY}/… → 媒体/生成/{当前年月}/…（无 mtime；迁移用 path_map）
        if parts and is_year_only_period(parts[0]):
            tail = "/".join(parts[1:])
            return f"{media_generated_dir()}/{tail}" if tail else media_generated_dir()
        return f"{MEDIA_ROOT}/{MEDIA_GENERATED}/{rest}"
    year_only = parse_year_only_media_file(norm)
    if year_only is not None:
        track, _year, name = year_only
        dest = media_generated_dir() if track == "generated" else media_upload_dir()
        return f"{dest}/{name}"
    if is_legacy_inbox_image_path(norm):
        name = PurePosixPath(norm).name
        # 无 mtime / path_map 时落到当前年月；迁移应用 path_map 覆盖
        return f"{media_upload_dir()}/{name}"
    if "/" not in norm and is_image_filename(norm):
        return f"{media_upload_dir()}/{norm}"
    return norm


def apply_legacy_media_rewrites(text: str, path_map: dict[str, str] | None = None) -> str:
    """对任意字符串做旧媒体路径替换（整路径优先，其次子串）。"""
    mapping = path_map or {}
    if text in mapping:
        return mapping[text]
    out = text
    for old, new in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        if old in out:
            out = out.replace(old, new)
    as_path = rewrite_legacy_media_path(out, path_map=mapping)
    if as_path != out:
        return as_path
    legacy_prefix = f"{LEGACY_GENERATED_ROOT}/"
    new_prefix = f"{MEDIA_ROOT}/{MEDIA_GENERATED}/"
    if legacy_prefix in out:
        out = out.replace(legacy_prefix, new_prefix)
        # 前缀替换后可能仍带 {年} 段，再走一次路径改写
        as_path2 = rewrite_legacy_media_path(out, path_map=mapping)
        if as_path2 != out:
            return as_path2
    return out


def _rewrite_json_value(value: Any, path_map: dict[str, str]) -> Any:
    if isinstance(value, str):
        return apply_legacy_media_rewrites(value, path_map)
    if isinstance(value, list):
        return [_rewrite_json_value(v, path_map) for v in value]
    if isinstance(value, dict):
        return {k: _rewrite_json_value(v, path_map) for k, v in value.items()}
    return value


def rewrite_json_media_paths(raw: str | None, path_map: dict[str, str]) -> str | None:
    """重写 attachments_json / timeline_json 文本中的旧媒体路径。"""
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        text = apply_legacy_media_rewrites(raw, path_map)
        return text if text != raw else raw
    rewritten = _rewrite_json_value(data, path_map)
    new_raw = json.dumps(rewritten, ensure_ascii=False)
    return new_raw if new_raw != raw else raw
