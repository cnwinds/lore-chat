"""入站富媒体落到现有 attachments（知识库「媒体/上传」相对路径）。"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.engine.channel_plugins.types import InboundMedia
from app.storage.kb_media_paths import media_upload_dir

_log = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+")


def _safe_filename(name: str | None, *, fallback: str = "file.bin") -> str:
    raw = (name or "").strip() or fallback
    base = Path(raw.replace("\\", "/")).name or fallback
    cleaned = _SAFE_NAME.sub("_", base).strip("._") or fallback
    return cleaned[:80]


def _ext_from_mime(mime: str | None) -> str:
    table = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "audio/amr": ".amr",
        "audio/mpeg": ".mp3",
        "video/mp4": ".mp4",
        "application/pdf": ".pdf",
    }
    return table.get((mime or "").split(";")[0].strip().lower(), "")


def _filename_for(item: InboundMedia, index: int) -> str:
    name = _safe_filename(item.filename, fallback=f"file-{index + 1}.bin")
    if "." not in name:
        name += _ext_from_mime(item.mime) or ".bin"
    return name


def materialize_media(
    kb_path: str | Path | None,
    instance_id: str,
    items: list[InboundMedia] | None,
    *,
    downloader=None,
) -> list[str]:
    if not kb_path or not items:
        return []
    root = Path(kb_path)
    folder = media_upload_dir()
    dest_dir = root / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: list[str] = []
    for idx, item in enumerate(items):
        data = item.data
        if data is None and downloader is not None:
            try:
                data = downloader(item)
            except Exception:
                _log.warning(
                    "channel media download failed instance=%s file=%s",
                    instance_id,
                    item.filename,
                    exc_info=True,
                )
                data = None
        if not data:
            continue
        name = _filename_for(item, idx)
        rel = f"{folder}/ch_{instance_id}_{uuid.uuid4().hex[:8]}_{name}"
        abs_p = root / rel
        abs_p.parent.mkdir(parents=True, exist_ok=True)
        abs_p.write_bytes(data)
        out.append(rel)
    return out


def guess_filename_from_url(url: str | None, *, fallback: str = "image.jpg") -> str:
    if not url:
        return fallback
    path = urlparse(url).path
    return _safe_filename(Path(path).name, fallback=fallback)


def as_media_list(raw: Any) -> list[InboundMedia]:
    if not raw:
        return []
    out: list[InboundMedia] = []
    for item in raw:
        if isinstance(item, InboundMedia):
            out.append(item)
        elif isinstance(item, dict):
            name = str(item.get("filename") or item.get("name") or "file.bin")
            data = item.get("data")
            if isinstance(data, str):
                data = data.encode("utf-8")
            out.append(
                InboundMedia(
                    filename=name,
                    kind=str(item.get("kind") or "image"),
                    mime=item.get("mime"),
                    data=data if isinstance(data, (bytes, bytearray)) else None,
                    url=item.get("url"),
                    file_key=item.get("file_key"),
                )
            )
    return out
