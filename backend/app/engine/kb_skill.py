from __future__ import annotations

from app.engine.disclosure import disclose
from app.storage.repo import KnowledgeRepo

_SKILL_ENTRY = "SKILL.md"


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


def build_skill_activation_body(
    repo: KnowledgeRepo, root: str, *, limit: int
) -> tuple[str, str] | None:
    """返回 (entry_path, activation_text)；包无效时返回 None。"""
    try:
        entry = skill_entry_rel_path(root)
    except ValueError:
        return None
    try:
        doc = repo.read_doc(entry)
    except FileNotFoundError:
        return None
    info = disclose(doc.body, offset=0, limit=limit, with_outline=True)
    meta_bits: list[str] = [f"包根: {root}"]
    for key in ("name", "description", "title"):
        val = doc.meta.get(key)
        if val:
            meta_bits.append(f"{key}: {val}")
    header = "\n".join(meta_bits)
    body = info["body"]
    more = ""
    if info.get("has_more"):
        more = (
            f"\n\n（入口未读完，共约 {info['total_chars']} 字；"
            f"请对 `{entry}` 使用 read_doc 续读。`references/` 等子文件按需 read_doc，勿预读。）"
        )
    text = f"{header}\n\n{body}{more}"
    return entry, text
