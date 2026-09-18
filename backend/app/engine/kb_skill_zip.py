"""Skill 压缩包：与知识库目录下载 zip 对仗的安全解包。"""

from __future__ import annotations

import io
import zipfile
from pathlib import PurePosixPath

MAX_SKILL_ZIP_FILES = 500
MAX_SKILL_ZIP_BYTES = 80 * 1024 * 1024

_SKIP_NAMES = frozenset({".ds_store", "thumbs.db", "desktop.ini"})


def is_zip_filename(filename: str) -> bool:
    return PurePosixPath(str(filename).replace("\\", "/")).suffix.lower() == ".zip"


def skill_zip_package_name(filename: str) -> str:
    """压缩包文件名去掉 .zip 后作为 Skill 包文件夹名。"""
    base = PurePosixPath(str(filename).replace("\\", "/")).name.strip()
    if not base or base in (".", ".."):
        raise ValueError("无效文件名")
    if base.lower().endswith(".zip"):
        base = base[:-4].strip()
    if not base or base in (".", "..") or "/" in base or "\\" in base:
        raise ValueError("无效文件名")
    return base


def _is_skill_md_name(name: str) -> bool:
    return PurePosixPath(name).name.upper() == "SKILL.MD"


def _normalize_member(name: str) -> str | None:
    """安全相对路径；垃圾/隐藏文件返回 None；zip-slip 抛 ValueError。"""
    posix = name.replace("\\", "/").lstrip("/")
    if not posix:
        return None
    parts: list[str] = []
    for seg in posix.split("/"):
        if not seg or seg == ".":
            continue
        if seg == "..":
            raise ValueError(f"压缩包内路径不合法：{name}")
        if ":" in seg:
            raise ValueError(f"压缩包内路径不合法：{name}")
        if seg.startswith(".") or seg == "__MACOSX":
            return None
        parts.append(seg)
    if not parts:
        return None
    filename = parts[-1]
    if filename.lower() in _SKIP_NAMES or filename.startswith("._"):
        return None
    return "/".join(parts)


def _strip_common_wrapper(rels: list[str]) -> list[str]:
    """若所有文件都在同一顶层目录内（与 download-zip 的 `{folder}/…` 对仗），剥掉该层。"""
    if not rels:
        return rels
    tops = {rel.split("/", 1)[0] for rel in rels}
    if len(tops) != 1:
        return rels
    if not all("/" in rel for rel in rels):
        return rels
    stripped = [rel.split("/", 1)[1] for rel in rels]
    if any(not inner for inner in stripped):
        return rels
    return stripped


def _canonicalize_inner(rel: str) -> str:
    parts = rel.split("/")
    if _is_skill_md_name(parts[-1]):
        parts[-1] = "SKILL.md"
    return "/".join(parts)


def parse_skill_zip_entries(
    data: bytes, *, require_skill_md: bool = True
) -> list[tuple[str, bytes]]:
    """读取目录 zip：剥包装目录、跳过垃圾与打包 meta、拒绝路径穿越。

    返回 ``(包内相对路径, 字节)``，其中 SKILL.md 文件名已规范。
    """
    if not data:
        raise ValueError("压缩包是空的")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.LargeZipFile as e:
        raise ValueError("技能压缩包过大") from e
    except (zipfile.BadZipFile, OSError) as e:
        raise ValueError("不是有效的 zip 压缩包") from e

    from app.engine.kb_pack import is_pack_meta_name

    members: list[tuple[str, zipfile.ZipInfo]] = []
    for info in zf.infolist():
        filename = info.filename.replace("\\", "/")
        if info.is_dir() or filename.endswith("/"):
            continue
        rel = _normalize_member(filename)
        if rel is None or is_pack_meta_name(rel):
            continue
        members.append((rel, info))

    if not members:
        raise ValueError("压缩包内没有可导入的文件")
    if len(members) > MAX_SKILL_ZIP_FILES:
        raise ValueError("压缩包内文件过多")

    inners = _strip_common_wrapper([rel for rel, _ in members])
    total = 0
    out: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    for (_orig, info), inner in zip(members, inners, strict=True):
        inner = _canonicalize_inner(inner)
        if not inner:
            continue
        if inner in seen:
            raise ValueError(f"压缩包内路径重复：{inner}")
        seen.add(inner)
        if info.file_size < 0 or info.file_size > MAX_SKILL_ZIP_BYTES:
            raise ValueError("技能压缩包过大")
        try:
            payload = zf.read(info)
        except zipfile.LargeZipFile as e:
            raise ValueError("技能压缩包过大") from e
        except (RuntimeError, zipfile.BadZipFile, OSError) as e:
            raise ValueError("无法读取压缩包") from e
        if len(payload) > MAX_SKILL_ZIP_BYTES:
            raise ValueError("技能压缩包过大")
        total += max(info.file_size, len(payload))
        if total > MAX_SKILL_ZIP_BYTES:
            raise ValueError("技能压缩包过大")
        out.append((inner, payload))

    if not out:
        raise ValueError("压缩包内没有可导入的文件")
    if require_skill_md and not any(_is_skill_md_name(path) for path, _ in out):
        raise ValueError("技能压缩包须包含 SKILL.md")
    return out
