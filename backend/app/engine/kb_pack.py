"""知识库目录打包元数据：下载 zip 写入，上传时识别 skill / 普通目录包。"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from typing import Literal

from app.engine.kb_skill import is_under_dir, norm_dir
from app.storage.kb_paths import KbPathError, join_kb_directory, normalize_directory

PACK_FORMAT = "lorechat.kb-pack"
PACK_VERSION = 1
PACK_META_NAMES = frozenset({"lorechat-pack.json", ".lorechat-pack.json"})
MAX_PACK_META_BYTES = 64 * 1024

PackKind = Literal["skill", "directory"]


class PackPathChoiceError(ValueError):
    """打包路径与拖入位置不同：前端应让用户选择，默认拖入位置。"""

    def __init__(
        self,
        *,
        kind: PackKind,
        original_path: str,
        upload_path: str,
        skills_dir: str,
    ):
        self.kind = kind
        self.original_path = original_path
        self.upload_path = upload_path
        self.default_path = upload_path
        self.skills_dir = skills_dir
        super().__init__(
            f"这个压缩包原来的位置是「{original_path}」，"
            f"你拖到了「{upload_path}」。请选择解压到哪一条路径。"
        )


@dataclass(frozen=True)
class KbPackMeta:
    kind: PackKind
    rel_path: str
    name: str
    skills_rel: str = ""


def is_pack_meta_name(rel: str) -> bool:
    base = rel.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return base in PACK_META_NAMES


def dump_pack_meta(meta: KbPackMeta) -> bytes:
    payload = {
        "format": PACK_FORMAT,
        "version": PACK_VERSION,
        "kind": meta.kind,
        "rel_path": meta.rel_path,
        "name": meta.name,
    }
    if meta.kind == "skill":
        payload["skills_rel"] = meta.skills_rel
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def pack_meta_for_directory(dir_rel: str, *, skills_dir: str = "技能") -> KbPackMeta:
    rel = normalize_directory(dir_rel)
    if not rel:
        raise ValueError("不能打包知识库根目录")
    name = rel.rsplit("/", 1)[-1]
    skills = norm_dir(skills_dir) or "技能"
    if is_under_dir(rel, skills):
        skills_rel = "" if rel == skills else rel[len(skills) + 1 :]
        return KbPackMeta(
            kind="skill", rel_path=rel, name=name, skills_rel=skills_rel
        )
    return KbPackMeta(kind="directory", rel_path=rel, name=name)


def _join_rel(base: str, rel: str) -> str:
    cur = normalize_directory(base)
    extra = normalize_directory(rel)
    if not extra:
        return cur
    for seg in extra.split("/"):
        cur = join_kb_directory(cur, seg)
    return cur


def original_unpack_path(meta: KbPackMeta, *, skills_dir: str) -> str:
    """meta 中的原始路径；技能包按当前技能目录重定位。"""
    if meta.kind == "skill":
        skills = norm_dir(skills_dir) or "技能"
        rel = (meta.skills_rel or "").replace("\\", "/").strip("/")
        if not rel:
            return skills
        try:
            return _join_rel(skills, rel)
        except KbPathError as e:
            raise ValueError(str(e)) from e
    return meta.rel_path


def upload_unpack_path(*, drop_dir: str, filename: str) -> str:
    """用户拖入位置：拖放目录 + zip 文件名（去掉 .zip）。"""
    from app.engine.kb_skill_zip import skill_zip_package_name

    leaf = skill_zip_package_name(filename)
    drop = normalize_directory(drop_dir)
    if not drop:
        return join_kb_directory("", leaf)
    return join_kb_directory(drop, leaf)


def read_pack_meta(data: bytes) -> KbPackMeta | None:
    """读取 zip 根目录的打包元数据；无此文件则 None（按普通 zip 文件保存）。"""
    if not data:
        return None
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError):
        return None
    raw: bytes | None = None
    try:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/").lstrip("/")
            if "/" in name or info.is_dir() or name.endswith("/"):
                continue
            if name in PACK_META_NAMES:
                if info.file_size < 0 or info.file_size > MAX_PACK_META_BYTES:
                    raise ValueError("打包信息过大")
                try:
                    raw = zf.read(info)
                except (RuntimeError, zipfile.BadZipFile, OSError) as e:
                    raise ValueError("无法读取打包信息") from e
                if len(raw) > MAX_PACK_META_BYTES:
                    raise ValueError("打包信息过大")
                break
    finally:
        zf.close()
    if raw is None:
        return None
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError("打包信息不是有效 JSON") from e
    if not isinstance(obj, dict):
        raise ValueError("打包信息无效")
    if obj.get("format") != PACK_FORMAT:
        return None
    if obj.get("version") != PACK_VERSION:
        raise ValueError(f"不支持的打包格式版本：{obj.get('version')}")
    kind = obj.get("kind")
    if kind not in ("skill", "directory"):
        raise ValueError("打包信息缺少 kind")
    try:
        rel_path = normalize_directory(str(obj.get("rel_path") or ""))
    except KbPathError as e:
        raise ValueError(str(e)) from e
    if not rel_path:
        raise ValueError("打包信息缺少 rel_path")
    name = str(obj.get("name") or "").strip() or rel_path.rsplit("/", 1)[-1]
    skills_rel = ""
    if kind == "skill":
        try:
            skills_rel = normalize_directory(str(obj.get("skills_rel") or ""))
        except KbPathError as e:
            raise ValueError(str(e)) from e
    return KbPackMeta(
        kind=kind, rel_path=rel_path, name=name, skills_rel=skills_rel
    )
