from __future__ import annotations

import sqlite3
from pathlib import Path

_CONVERSATIONS_DB_REL = Path(".kb") / "conversations" / "conversations.db"


def is_kb_empty(
    kb_path: Path,
    system_layer_dir: str = "系统",
    skills_dir: str = "技能",
) -> bool:
    """Return True when the knowledge base has no user content."""
    root = Path(kb_path)
    if _has_conversations(root):
        return False
    if _has_user_markdown(root, system_layer_dir, skills_dir):
        return False
    if _has_user_files(root, system_layer_dir, skills_dir):
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


def _skills_seed_rel(skills_dir: str) -> str:
    return f"{skills_dir.rstrip('/')}/.gitkeep"


def _has_user_markdown(
    root: Path, system_layer_dir: str, skills_dir: str = "技能"
) -> bool:
    system_prefix = system_layer_dir.rstrip("/") + "/"
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".kb/"):
            continue
        if rel.startswith(system_prefix):
            continue
        return True
    return False


def _has_user_files(
    root: Path, system_layer_dir: str, skills_dir: str = "技能"
) -> bool:
    """非 Markdown 用户文件（任意后缀），不计 .kb/.git/系统层/技能目录播种文件。"""
    system_prefix = system_layer_dir.rstrip("/") + "/"
    skills_seed = _skills_seed_rel(skills_dir)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".kb/") or rel.startswith(".git/"):
            continue
        if rel.startswith(system_prefix):
            continue
        if rel == skills_seed:
            continue
        if rel.lower().endswith(".md"):
            continue
        return True
    return False
