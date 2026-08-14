from __future__ import annotations

import sqlite3
import zipfile
from io import BufferedIOBase
from pathlib import Path
from typing import BinaryIO

from app.backup.manifest import build_manifest, manifest_json

_EXCLUDED_DB_NAMES = frozenset({"fts.db", "conversation_fts.db"})
_VEC_PREFIX = ".kb/index/vec"


def _normalize_rel(rel: str) -> str:
    return rel.replace("\\", "/")


def _should_exclude(rel: str) -> bool:
    posix = _normalize_rel(rel)
    if posix == "manifest.json":
        return True
    if posix == _VEC_PREFIX or posix.startswith(f"{_VEC_PREFIX}/"):
        return True
    name = Path(posix).name
    if name in _EXCLUDED_DB_NAMES:
        return True
    if name.endswith(".db-wal") or name.endswith(".db-shm"):
        return True
    return False


def _checkpoint_sqlite_dbs(kb_path: Path) -> None:
    for path in kb_path.rglob("*.db"):
        rel = path.relative_to(kb_path).as_posix()
        if _should_exclude(rel):
            continue
        try:
            conn = sqlite3.connect(str(path), timeout=5)
        except sqlite3.Error:
            continue
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        finally:
            conn.close()


def _iter_export_files(kb_path: Path):
    for path in sorted(kb_path.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(kb_path).as_posix()
        if _should_exclude(rel):
            continue
        yield rel, path


def build_export_zip(kb_path: Path, dest: Path | BinaryIO) -> None:
    root = Path(kb_path)
    if not root.is_dir():
        raise FileNotFoundError(f"knowledge base path not found: {root}")

    _checkpoint_sqlite_dbs(root)
    manifest = build_manifest(root)

    if isinstance(dest, Path):
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            _write_zip(zf, root, manifest)
        return

    if isinstance(dest, BufferedIOBase):
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            _write_zip(zf, root, manifest)
        return

    raise TypeError("dest must be a Path or binary stream")


def _write_zip(zf: zipfile.ZipFile, kb_path: Path, manifest: dict) -> None:
    zf.writestr("manifest.json", manifest_json(manifest))
    for rel, path in _iter_export_files(kb_path):
        zf.write(path, rel)


def _kb_user_file(rel: str, path: Path) -> bool:
    if _should_exclude(rel):
        return False
    if rel.startswith(".kb/") or rel.startswith(".git/"):
        return False
    if path.name == ".gitkeep":
        return False
    return True


def build_directory_zip(kb_path: Path, dir_rel: str, dest: Path | BinaryIO) -> str:
    """Pack one knowledge-base directory; zip entries are `{folder_name}/…`. Returns base filename."""
    root = Path(kb_path)
    norm = _normalize_rel(dir_rel).strip("/")
    if not norm or norm.startswith(".kb/") or norm.startswith(".git/"):
        raise FileNotFoundError(dir_rel)

    base = root / norm
    if not base.exists():
        raise FileNotFoundError(dir_rel)
    if not base.is_dir():
        raise NotADirectoryError(dir_rel)

    folder_name = norm.rsplit("/", 1)[-1]
    entries: list[tuple[str, Path]] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if not _kb_user_file(rel, path):
            continue
        inner = path.relative_to(base).as_posix()
        entries.append((f"{folder_name}/{inner}", path))

    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if not entries:
            zf.writestr(f"{folder_name}/", b"")
        for arcname, path in entries:
            zf.write(path, arcname)
    return folder_name
