"""Skill 固定目录：播种与路径归属。"""

from __future__ import annotations

from app.engine.kb_skill import is_under_dir, norm_dir
from app.storage.repo import KnowledgeRepo


def ensure_skills_dir(repo: KnowledgeRepo, skills_dir: str) -> str:
    """若缺失则创建空技能目录（.gitkeep，list_tree 不展示该文件）。"""
    name = norm_dir(skills_dir) or "技能"
    abs_dir = repo.abs_path(name)
    abs_dir.mkdir(parents=True, exist_ok=True)
    keep = abs_dir / ".gitkeep"
    if not keep.exists():
        keep.write_text("", encoding="utf-8")
        try:
            repo.repo.index.add([f"{name}/.gitkeep"])
            if repo.repo.is_dirty(index=True):
                repo.repo.index.commit(f"seed skills dir: {name}")
        except Exception:
            pass
    return name


def clamp_skills_scan_dir(from_dir: str, skills_dir: str) -> str:
    """将扫描起点规范到技能目录内；空则默认为技能根。越界则抛 ValueError。"""
    skills = norm_dir(skills_dir) or "技能"
    norm = norm_dir(from_dir)
    if not norm:
        return skills
    if not is_under_dir(norm, skills):
        raise ValueError(f"Skill 仅可在「{skills}」目录下发现")
    return norm
