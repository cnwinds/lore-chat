"""Skill 固定目录：播种、扫描钳制、路径硬约束。"""

from __future__ import annotations

from pathlib import PurePosixPath

from app.engine.kb_skill import is_under_dir, norm_dir, skill_package_root_from_skill_md
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


def is_skills_path(path: str, skills_dir: str) -> bool:
    return is_under_dir(path, skills_dir)


def is_skill_md_path(rel_path: str) -> bool:
    return PurePosixPath(rel_path.replace("\\", "/")).name.upper() == "SKILL.MD"


def require_skill_root_in_skills_dir(root: str, skills_dir: str) -> None:
    """skill_root 必须为「技能」下的非空包根。"""
    skills = norm_dir(skills_dir) or "技能"
    root_n = norm_dir(root)
    if not root_n or not is_under_dir(root_n, skills):
        raise ValueError(f"Skill 包必须位于「{skills}」目录下")


def require_skill_md_in_skills_dir(rel_path: str, skills_dir: str) -> None:
    """写入/移动 SKILL.md 时路径必须落在技能目录包内。"""
    if not is_skill_md_path(rel_path):
        return
    skills = norm_dir(skills_dir) or "技能"
    root = skill_package_root_from_skill_md(rel_path)
    if root is None or not is_under_dir(root, skills):
        raise ValueError(f"SKILL.md 只能写在「{skills}」目录下的 Skill 包内")
