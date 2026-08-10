"""识图：把本地附件编成 multimodal content（data URL 或签名 HTTP URL）。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import mimetypes
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.models.candidate import ImageWire, ModelCandidate

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".ico"}


def is_image_path(path: str) -> bool:
    """按 MIME（mimetypes）判断；无映射时回退常见图片后缀。"""
    mime, _ = mimetypes.guess_type(path)
    if mime and mime.startswith("image/"):
        return True
    return Path(path).suffix.lower() in _IMAGE_SUFFIXES


def sniff_image_mime(path: Path) -> str | None:
    try:
        head = path.read_bytes()[:16]
    except OSError:
        return None
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "image/gif"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def is_image_file(path: Path) -> bool:
    """路径启发式或 magic；注入附件等宽松场景用。"""
    if is_image_path(str(path)):
        return True
    return sniff_image_mime(path) is not None


def is_signed_image_file(path: Path) -> bool:
    """签名 URL 出口：必须 magic 命中，禁止仅靠后缀伪装。"""
    return sniff_image_mime(path) is not None


def guess_mime(path: str) -> str:
    sniffed = sniff_image_mime(Path(path))
    if sniffed:
        return sniffed
    mime, _ = mimetypes.guess_type(path)
    if mime and mime.startswith("image/"):
        return mime
    return "image/jpeg"


def attachment_signing_secret(settings: Any) -> str:
    key = (
        getattr(settings, "openai_api_key", None)
        or getattr(settings, "embed_api_key", None)
        or "lorechat-attachment"
    )
    text = str(key).strip()
    return text or "lorechat-attachment"


def sign_attachment_token(
    *,
    rel_path: str,
    secret: str,
    ttl_sec: int = 600,
    now: float | None = None,
) -> str:
    now = time.time() if now is None else now
    exp = int(now + ttl_sec)
    msg = f"{rel_path}:{exp}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:32]
    return f"{exp}.{sig}"


def verify_attachment_token(
    *,
    rel_path: str,
    token: str,
    secret: str,
    now: float | None = None,
) -> bool:
    now = time.time() if now is None else now
    try:
        exp_s, sig = token.split(".", 1)
        exp = int(exp_s)
    except ValueError:
        return False
    if exp < now:
        return False
    msg = f"{rel_path}:{exp}".encode()
    want = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(want, sig)


def attachment_is_image(rel_path: str, *, kb_path: Path | None = None) -> bool:
    """优先按磁盘文件 MIME/magic；否则回退路径 MIME/后缀。"""
    if kb_path is not None:
        abs_p = (Path(kb_path) / rel_path).resolve()
        if abs_p.is_file():
            return is_image_file(abs_p)
    return is_image_path(rel_path)


def build_image_url(
    *,
    public_base_url: str,
    rel_path: str,
    token: str,
) -> str:
    base = public_base_url.rstrip("/")
    return f"{base}/api/attachments/signed/{quote(rel_path, safe='/')}?token={token}"


def file_to_data_url(path: Path) -> str:
    raw = path.read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    mime = guess_mime(str(path))
    return f"data:{mime};base64,{b64}"


def build_user_content_with_images(
    text: str,
    attachment_paths: list[str],
    *,
    candidate: ModelCandidate,
    kb_path: Path,
    public_base_url: str | None,
    signing_secret: str,
) -> str | list[dict[str, Any]]:
    """返回 OpenAI-style content：无图则纯字符串；有图则 parts 列表。"""
    image_rels: list[str] = []
    other: list[str] = []
    for p in attachment_paths:
        abs_try = (kb_path / p).resolve()
        if abs_try.is_file() and is_image_file(abs_try):
            image_rels.append(p)
        elif is_image_path(p):
            image_rels.append(p)
        else:
            other.append(p)
    text_parts = []
    if other:
        text_parts.append("（附件：" + "、".join(other) + "）")
    text_parts.append(text)
    body = "\n\n".join(text_parts)

    if not image_rels or not candidate.image:
        if image_rels:
            # 模型无识图：路径写进文本
            prefix = "（图片附件未能送入模型：" + "、".join(image_rels) + "）\n\n"
            return prefix + body
        return body

    wire: ImageWire = candidate.image_wire
    parts: list[dict[str, Any]] = [{"type": "text", "text": body}]
    for rel in image_rels:
        abs_path = (kb_path / rel).resolve()
        if not abs_path.is_file():
            continue
        if wire == "url":
            base = (public_base_url or "").strip()
            if not base:
                continue
            token = sign_attachment_token(rel_path=rel, secret=signing_secret)
            url = build_image_url(public_base_url=base, rel_path=rel, token=token)
        else:
            url = file_to_data_url(abs_path)
        parts.append({"type": "image_url", "image_url": {"url": url}})
    if len(parts) == 1:
        return body
    return parts
