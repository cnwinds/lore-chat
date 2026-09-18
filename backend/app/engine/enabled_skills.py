"""跨会话启用的 Skill 包根列表（.kb/enabled_skills.json）。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TypedDict

from app.engine.kb_skill import (
    norm_dir,
    skill_entry_rel_path,
    skill_trigger_fields,
)
from app.engine.skills_dir import require_skill_root_in_skills_dir
from app.storage.repo import KnowledgeRepo

_log = logging.getLogger(__name__)


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

    def try_enable_root(self, repo: KnowledgeRepo, root: str) -> bool:
        """新包加入启用集：已在集内或触发头不齐则跳过，不抛错。"""
        root_n = norm_dir(root)
        if not root_n:
            return False
        current = self.load_roots()
        if root_n in current:
            return False
        try:
            build_skill_catalog(repo, [root_n], skills_dir=self.skills_dir)
        except EnabledSkillsError:
            return False
        self.save_roots([*current, root_n])
        return True

    def remap_roots(self, from_path: str, to_path: str) -> list[str]:
        """目录/包搬家时改写启用集路径（前缀匹配，避免误伤同名前缀）。"""
        from_n = norm_dir(from_path)
        to_n = norm_dir(to_path)
        roots = self.load_roots()
        if not from_n or not to_n or from_n == to_n:
            return roots
        out: list[str] = []
        changed = False
        for root in roots:
            if root == from_n or root.startswith(f"{from_n}/"):
                suffix = root[len(from_n) :].lstrip("/")
                mapped = f"{to_n}/{suffix}" if suffix else to_n
                out.append(mapped)
                if mapped != root:
                    changed = True
            else:
                out.append(root)
        if changed:
            return self.save_roots(out)
        return roots

    def prune_missing_packages(self, repo: KnowledgeRepo) -> list[str]:
        """去掉已不存在或越出技能目录的包根；SKILL.md 还在则保留。"""
        before = self.load_roots()
        kept: list[str] = []
        dropped: list[str] = []
        for root in before:
            try:
                require_skill_root_in_skills_dir(root, self.skills_dir)
                entry = skill_entry_rel_path(root)
            except ValueError:
                dropped.append(root)
                continue
            if repo.abs_path(entry).is_file():
                kept.append(root)
            else:
                dropped.append(root)
        if dropped:
            _log.info("启用集去掉已不存在的 Skill 包：%s", "、".join(dropped))
            return self.save_roots(kept)
        return before

    def catalog_for_chat(self, repo: KnowledgeRepo) -> list[SkillCatalogEntry]:
        """加载启用集并校验触发头；缺包只跳过（启用集可能残留已删目录）。"""
        return build_skill_catalog(
            repo,
            self.load_roots(),
            skills_dir=self.skills_dir,
            drop_missing=True,
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
    drop_missing: bool = False,
) -> list[SkillCatalogEntry]:
    """校验包存在且正文 YAML 含 name/description；返回 catalog 条目。

    drop_missing：对话装配时跳过已删/越界包，避免启用集残留挡整轮。
    PUT 启用集仍须严格失败。缺 name/description 的现存包始终报错。
    """
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
        if not drop_missing:
            raise EnabledSkillsError(
                f"以下 Skill 包无效（须在「{skills}」下且含 SKILL.md）："
                + "、".join(missing_pkgs)
            )
        _log.warning("跳过无效 Skill 包（启用集残留）：%s", "、".join(missing_pkgs))
    if problems:
        raise EnabledSkillsError(format_skill_header_errors(problems))
    return catalog
