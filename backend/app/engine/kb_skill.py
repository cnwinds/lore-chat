from __future__ import annotations

import re

import yaml

from app.storage.repo import KnowledgeRepo

_SKILL_ENTRY = "SKILL.md"
_BODY_YAML = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", re.DOTALL)


def norm_dir(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def is_under_dir(path: str, base: str) -> bool:
    base = norm_dir(base)
    path = norm_dir(path)
    if not base:
        return True
    return path == base or path.startswith(f"{base}/")


def skill_package_root_from_skill_md(rel_path: str) -> str | None:
    """含 SKILL.md 的包根；知识库根目录的 SKILL.md 不视为合法包。"""
    rel = rel_path.replace("\\", "/")
    if rel == _SKILL_ENTRY:
        return None
    suffix = f"/{_SKILL_ENTRY}"
    if rel.endswith(suffix):
        root = rel[: -len(suffix)]
        return root if root else None
    return None


def discover_skill_roots(
    repo: KnowledgeRepo,
    from_dir: str,
    *,
    skills_dir: str,
) -> list[str]:
    """递归找出 from_dir 下（含自身）所有含 SKILL.md 的目录包根；仅限 skills_dir 内。"""
    from_dir = norm_dir(from_dir)
    skills = norm_dir(skills_dir)
    if not skills:
        raise ValueError("skills_dir 不能为空")
    roots: set[str] = set()
    for rel in repo.list_tree():
        root = skill_package_root_from_skill_md(rel)
        if root is None:
            continue
        if not is_under_dir(root, from_dir):
            continue
        if not is_under_dir(root, skills):
            continue
        roots.add(root)
    return sorted(roots)


def skill_entry_rel_path(root: str) -> str:
    root = norm_dir(root)
    if not root:
        raise ValueError("Skill 包根不能为空（禁止知识库根目录作为包）")
    return f"{root}/{_SKILL_ENTRY}"


def parse_skill_body_header(body: str) -> dict:
    """解析 SKILL.md 正文开头的 --- YAML（非 LORE_META）。"""
    text = (body or "").lstrip("\ufeff")
    m = _BODY_YAML.match(text)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _as_nonempty_str(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip()
        return s or None
    s = str(val).strip()
    return s or None


def skill_trigger_fields(body: str) -> tuple[str | None, str | None]:
    """从正文 YAML 取 name / description（触发条件）；忽略 KB meta。"""
    data = parse_skill_body_header(body)
    return _as_nonempty_str(data.get("name")), _as_nonempty_str(
        data.get("description")
    )
