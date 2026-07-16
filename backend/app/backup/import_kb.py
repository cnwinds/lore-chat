from __future__ import annotations

import json
import os
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Literal

from app.backup.empty import is_kb_empty
from app.backup.export_kb import build_export_zip
from app.backup.manifest import FORMAT_VERSION

ImportMode = Literal["empty_only", "overwrite"]


@dataclass
class ImportResult:
    ok: bool
    backup_path: Path | None
    message: str


def backup_dir_for(kb_path: Path) -> Path:
    env = os.environ.get("BACKUP_DIR")
    if env:
        return Path(env)
    return Path(kb_path).parent / "lorechat-backups"


def _validate_manifest(zf: zipfile.ZipFile) -> None:
    try:
        raw = zf.read("manifest.json")
    except KeyError as exc:
        raise ValueError("missing manifest.json") from exc
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid manifest.json") from exc
    version = manifest.get("format_version")
    if version != FORMAT_VERSION:
        raise ValueError(f"unsupported format_version: {version}")


def _clear_kb(kb_path: Path) -> None:
    root = Path(kb_path)
    root.mkdir(parents=True, exist_ok=True)
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _safe_dest(kb_path: Path, rel: str) -> Path:
    posix = rel.replace("\\", "/").lstrip("/")
    if not posix or ".." in posix.split("/"):
        raise ValueError(f"unsafe path in zip: {rel}")
    dest = (kb_path / posix).resolve()
    if not dest.is_relative_to(kb_path.resolve()):
        raise ValueError(f"unsafe path in zip: {rel}")
    return dest


def _extract_zip(zf: zipfile.ZipFile, kb_path: Path) -> None:
    root = Path(kb_path)
    root.mkdir(parents=True, exist_ok=True)
    for name in zf.namelist():
        if name.endswith("/"):
            continue
        dest = _safe_dest(root, name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(name) as src, open(dest, "wb") as dst:
            shutil.copyfileobj(src, dst)


def _stage_zip(zf: zipfile.ZipFile, kb_path: Path) -> Path:
    staging = kb_path.parent / f".import-staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        _extract_zip(zf, staging)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return staging


def _promote_staging(staging: Path, kb_path: Path) -> None:
    _clear_kb(kb_path)
    for child in staging.iterdir():
        dest = kb_path / child.name
        shutil.move(str(child), str(dest))
    shutil.rmtree(staging, ignore_errors=True)


def _backup_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def import_kb(
    kb_path: Path,
    zip_path: Path | BinaryIO,
    mode: ImportMode,
    *,
    system_layer_dir: str = "系统",
) -> ImportResult:
    root = Path(kb_path)
    root.mkdir(parents=True, exist_ok=True)

    if mode == "empty_only":
        if not is_kb_empty(root, system_layer_dir):
            return ImportResult(
                ok=False,
                backup_path=None,
                message="knowledge base is not empty",
            )
        try:
            with zipfile.ZipFile(zip_path) as zf:
                _validate_manifest(zf)
                staging = _stage_zip(zf, root)
                _promote_staging(staging, root)
        except Exception as exc:
            return ImportResult(ok=False, backup_path=None, message=str(exc))
        return ImportResult(ok=True, backup_path=None, message="imported")

    backup_dir = backup_dir_for(root)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"kb-backup-{_backup_timestamp()}.zip"

    try:
        build_export_zip(root, backup_path)
    except Exception as exc:
        return ImportResult(
            ok=False,
            backup_path=None,
            message=f"backup failed: {exc}",
        )

    try:
        with zipfile.ZipFile(zip_path) as zf:
            _validate_manifest(zf)
            staging = _stage_zip(zf, root)
            try:
                _promote_staging(staging, root)
            except Exception as exc:
                _clear_kb(root)
                with zipfile.ZipFile(backup_path) as backup_zip:
                    _extract_zip(backup_zip, root)
                return ImportResult(
                    ok=False,
                    backup_path=backup_path,
                    message=f"import failed, rolled back: {exc}",
                )
    except Exception as exc:
        return ImportResult(
            ok=False,
            backup_path=backup_path,
            message=str(exc),
        )

    return ImportResult(
        ok=True,
        backup_path=backup_path,
        message="imported with backup",
    )
