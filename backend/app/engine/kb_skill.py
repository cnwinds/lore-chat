from __future__ import annotations

from app.engine.disclosure import disclose
from app.storage.repo import KnowledgeRepo

_SKILL_ENTRY = "SKILL.md"


def _norm_dir(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def is_under_dir(path: str, base: str) -> bool:
    base = _norm_dir(base)
    path = _norm_dir(path)
    if not base:
        return True
    return path == base or path.startswith(f"{base}/")


def skill_package_root_from_skill_md(rel_path: str) -> str | None:
    rel = rel_path.replace("\\", "/")
    if rel == _SKILL_ENTRY:
        return ""
    suffix = f"/{_SKILL_ENTRY}"
    if rel.endswith(suffix):
        return rel[: -len(suffix)]
    return None


def discover_skill_roots(repo: KnowledgeRepo, from_dir: str) -> list[str]:
    """递归找出 from_dir 下（含自身）所有含 SKILL.md 的目录包根。"""
    from_dir = _norm_dir(from_dir)
    roots: set[str] = set()
    for rel in repo.list_tree():
        root = skill_package_root_from_skill_md(rel)
        if root is None:
            continue
        if is_under_dir(root, from_dir):
            roots.add(root)
    return sorted(roots)


def skill_entry_rel_path(root: str) -> str:
    root = _norm_dir(root)
    return f"{root}/{_SKILL_ENTRY}" if root else _SKILL_ENTRY


def build_skill_activation_body(
    repo: KnowledgeRepo, root: str, *, limit: int
) -> tuple[str, str] | None:
    """返回 (entry_path, activation_text)；包无效时返回 None。"""
    entry = skill_entry_rel_path(root)
    try:
        doc = repo.read_doc(entry)
    except FileNotFoundError:
        return None
    info = disclose(doc.body, offset=0, limit=limit, with_outline=True)
    meta_bits: list[str] = [f"包根: {root or '(根目录)'}"]
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
