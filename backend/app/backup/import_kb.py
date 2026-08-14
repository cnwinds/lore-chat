from __future__ import annotations

import json
import os
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

from app.backup.empty import is_kb_empty
from app.backup.export_kb import build_export_zip
from app.backup.manifest import FORMAT_VERSION

ImportMode = Literal["empty_only", "overwrite"]
ImportFailureCode = Literal[
    "kb_not_empty",
    "unsupported_format",
    "invalid_manifest",
    "import_failed",
]


class KbImportError(ValueError):
    def __init__(self, message: str, code: ImportFailureCode) -> None:
        super().__init__(message)
        self.code = code


IMPORT_HTTP_STATUS: dict[ImportFailureCode, int] = {
    "kb_not_empty": 409,
    "unsupported_format": 409,
    "invalid_manifest": 422,
    "import_failed": 400,
}


@dataclass
class ImportResult:
    ok: bool
    backup_path: Path | None
    message: str
    code: ImportFailureCode | None = None

    def http_status(self) -> int:
        return IMPORT_HTTP_STATUS[self.code or "import_failed"]


def _fail(
    message: str,
    code: ImportFailureCode,
    backup_path: Path | None = None,
) -> ImportResult:
    return ImportResult(ok=False, backup_path=backup_path, message=message, code=code)


def _fail_from_exc(
    exc: BaseException, backup_path: Path | None = None
) -> ImportResult:
    if isinstance(exc, KbImportError):
        return _fail(str(exc), exc.code, backup_path)
    return _fail(str(exc), "import_failed", backup_path)


def backup_dir_for(kb_path: Path) -> Path:
    env = os.environ.get("BACKUP_DIR")
    if env:
        return Path(env)
    return Path(kb_path).parent / "lorechat-backups"


def _validate_manifest(zf: zipfile.ZipFile) -> None:
    try:
        raw = zf.read("manifest.json")
    except KeyError as exc:
        raise KbImportError("missing manifest.json", "invalid_manifest") from exc
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KbImportError("invalid manifest.json", "invalid_manifest") from exc
    version = manifest.get("format_version")
    if version != FORMAT_VERSION:
        raise KbImportError(
            f"unsupported format_version: {version}",
            "unsupported_format",
        )


def _children(src: Path, *, skip: set[str] | None = None):
    ignore = skip or set()
    for child in list(src.iterdir()):
        if child.name in ignore:
            continue
        yield child


def _clear_kb(kb_path: Path, *, skip: set[str] | None = None) -> None:
    root = Path(kb_path)
    root.mkdir(parents=True, exist_ok=True)
    for child in _children(root, skip=skip):
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _move_children(src: Path, dest: Path, *, skip: set[str] | None = None) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for child in _children(src, skip=skip):
        shutil.move(str(child), str(dest / child.name))


def _remove_empty_dir(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass


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
    """Replace kb_path *contents* with staging. Never rename kb_path itself.

    Docker bind-mounts ``KB_PATH`` (``/data/knowledge``); renaming the
    mountpoint fails with ``[Errno 16] Device or resource busy``.
    The vacate backup lives beside kb_path, not inside it, so a crash
    does not leave ``.import-kb-bak-*`` in the knowledge tree.
    """
    kb_path = Path(kb_path)
    staging = Path(staging)
    kb_path.mkdir(parents=True, exist_ok=True)
    bak = kb_path.parent / f".import-kb-bak-{uuid.uuid4().hex}"
    bak.mkdir(parents=True, exist_ok=False)
    replaced = False
    try:
        try:
            _move_children(kb_path, bak)
        except Exception:
            _move_children(bak, kb_path)
            raise
        try:
            _move_children(staging, kb_path)
        except Exception:
            _clear_kb(kb_path)
            _move_children(bak, kb_path)
            raise
        replaced = True
    finally:
        if replaced:
            shutil.rmtree(bak, ignore_errors=True)
        else:
            _remove_empty_dir(bak)
        shutil.rmtree(staging, ignore_errors=True)


def _stage_validated_zip(zip_path: Path | BinaryIO, kb_path: Path) -> Path:
    with zipfile.ZipFile(zip_path) as zf:
        _validate_manifest(zf)
        return _stage_zip(zf, kb_path)


def _backup_timestamp() -> str:
    from app.time import now_display

    return now_display().strftime("%Y%m%d-%H%M%S")


def import_kb(
    kb_path: Path,
    zip_path: Path | BinaryIO,
    mode: ImportMode,
    *,
    system_layer_dir: str = "系统",
    skills_dir: str = "技能",
) -> ImportResult:
    root = Path(kb_path)
    root.mkdir(parents=True, exist_ok=True)

    if mode == "empty_only":
        if not is_kb_empty(root, system_layer_dir, skills_dir):
            return _fail("knowledge base is not empty", "kb_not_empty")
        try:
            staging = _stage_validated_zip(zip_path, root)
            _promote_staging(staging, root)
        except Exception as exc:
            return _fail_from_exc(exc)
        return ImportResult(ok=True, backup_path=None, message="imported")

    backup_dir = backup_dir_for(root)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"kb-backup-{_backup_timestamp()}.zip"

    try:
        build_export_zip(root, backup_path)
    except Exception as exc:
        return _fail(f"backup failed: {exc}", "import_failed")

    try:
        staging = _stage_validated_zip(zip_path, root)
        try:
            _promote_staging(staging, root)
        except Exception as exc:
            _clear_kb(root)
            with zipfile.ZipFile(backup_path) as backup_zip:
                _extract_zip(backup_zip, root)
            return _fail(
                f"import failed, rolled back: {exc}",
                "import_failed",
                backup_path,
            )
    except Exception as exc:
        return _fail_from_exc(exc, backup_path)

    return ImportResult(
        ok=True,
        backup_path=backup_path,
        message="imported with backup",
    )
