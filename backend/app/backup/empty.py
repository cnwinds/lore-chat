from __future__ import annotations

import sqlite3
from pathlib import Path

_CONVERSATIONS_DB_REL = Path(".kb") / "conversations" / "conversations.db"
_ATTACHMENTS_MARKER = "/attachments/"


def is_kb_empty(kb_path: Path, system_layer_dir: str = "系统") -> bool:
    """Return True when the knowledge base has no user content."""
    root = Path(kb_path)
    if _has_conversations(root):
        return False
    if _has_user_markdown(root, system_layer_dir):
        return False
    if _has_attachments(root):
        return False
    return True


def _has_conversations(root: Path) -> bool:
    db_path = root / _CONVERSATIONS_DB_REL
    if not db_path.is_file():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM conversations").fetchone()
        return bool(row and row[0] > 0)
    finally:
        conn.close()


def _has_user_markdown(root: Path, system_layer_dir: str) -> bool:
    prefix = system_layer_dir.rstrip("/") + "/"
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".kb/"):
            continue
        if not rel.startswith(prefix):
            return True
    return False


def _has_attachments(root: Path) -> bool:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".kb/") or rel.startswith(".git/"):
            continue
        if _ATTACHMENTS_MARKER in f"/{rel}/":
            return True
    return False
