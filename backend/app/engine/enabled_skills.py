"""跨会话启用的 Skill 包根列表（.kb/enabled_skills.json）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from app.engine.kb_skill import (
    norm_dir,
    skill_entry_rel_path,
    skill_trigger_fields,
)
from app.engine.skills_dir import require_skill_root_in_skills_dir
from app.storage.repo import KnowledgeRepo


class EnabledSkillsError(ValueError):
    """启用集校验失败（缺包或缺触发头）。"""


class SkillCatalogEntry(TypedDict):
    root: str
    name: str
    description: str
    entry: str


class EnabledSkillsStore:
    def __init__(self, kb_path: Path, *, skills_dir: str = "技能"):
        self._path = Path(kb_path) / ".kb" / "enabled_skills.json"
        self.skills_dir = norm_dir(skills_dir) or "技能"

    def _clean_roots(self, roots: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in roots:
            root = norm_dir(str(item or ""))
            if not root or root in seen:
                continue
            seen.add(root)
            out.append(root)
        return out

    def load_roots(self) -> list[str]:
        if not self._path.is_file():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        roots = raw.get("roots") if isinstance(raw, dict) else None
        if not isinstance(roots, list):
            return []
        return self._clean_roots(roots)

    def save_roots(self, roots: list[str]) -> list[str]:
        cleaned = self._clean_roots(roots)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"roots": cleaned}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return cleaned

    def put(self, repo: KnowledgeRepo, roots: list[str]) -> list[str]:
        """校验并整表重写启用集。"""
        roots_in = list(roots or [])
        build_skill_catalog(repo, roots_in, skills_dir=self.skills_dir)
        return self.save_roots(roots_in)

    def catalog_for_chat(self, repo: KnowledgeRepo) -> list[SkillCatalogEntry]:
        """加载启用集并校验触发头；供 chat 注入。"""
        return build_skill_catalog(
            repo, self.load_roots(), skills_dir=self.skills_dir
        )


def format_skill_header_errors(problems: list[tuple[str, list[str]]]) -> str:
    """problems: (entry_path, missing_field_names)."""
    lines = [
        "以下 Skill 缺少触发头，请打开对应 SKILL.md，在正文开头用 --- YAML "
        "补全 name 与 description（description 为何时使用的触发条件，语言不限）："
    ]
    for entry, missing in problems:
        miss = "、".join(missing)
        lines.append(f"- `{entry}`（缺少 {miss}）")
    return "\n".join(lines)


def build_skill_catalog(
    repo: KnowledgeRepo,
    roots: list[str],
    *,
    skills_dir: str,
) -> list[SkillCatalogEntry]:
    """校验包存在且正文 YAML 含 name/description；返回 catalog 条目。"""
    skills = norm_dir(skills_dir) or "技能"
    problems: list[tuple[str, list[str]]] = []
    missing_pkgs: list[str] = []
    catalog: list[SkillCatalogEntry] = []
    for root in roots:
        root_n = norm_dir(root)
        try:
            require_skill_root_in_skills_dir(root_n, skills)
            entry = skill_entry_rel_path(root_n)
        except ValueError:
            missing_pkgs.append(root_n or root)
            continue
        if not repo.abs_path(entry).is_file():
            missing_pkgs.append(root_n)
            continue
        try:
            doc = repo.read_doc(entry)
        except FileNotFoundError:
            missing_pkgs.append(root_n)
            continue
        name, description = skill_trigger_fields(doc.body)
        missing_fields: list[str] = []
        if not name:
            missing_fields.append("name")
        if not description:
            missing_fields.append("description")
        if missing_fields:
            problems.append((entry, missing_fields))
            continue
        catalog.append(
            {
                "root": root_n,
                "name": name or "",
                "description": description or "",
                "entry": entry,
            }
        )
    if missing_pkgs:
        raise EnabledSkillsError(
            f"以下 Skill 包无效（须在「{skills}」下且含 SKILL.md）："
            + "、".join(missing_pkgs)
        )
    if problems:
        raise EnabledSkillsError(format_skill_header_errors(problems))
    return catalog
