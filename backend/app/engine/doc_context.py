from __future__ import annotations

from typing import Any, Literal

from app.engine.kb_skill import skill_entry_rel_path
from app.storage.repo import KnowledgeRepo

DocContextKind = Literal["document", "skill_root"]

_VALID_KINDS = frozenset({"document", "skill_root"})


class DocContextValidationError(ValueError):
    """聊天请求 doc_context 校验失败。"""


def normalize_doc_context_items(raw: list[Any] | None) -> list[dict[str, str]]:
    """从 DB 读出或兼容旧数据：字符串 → document；未知 kind → document。"""
    if not raw:
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, str):
            path = item.strip()
            if path:
                out.append({"path": path, "kind": "document"})
            continue
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        kind = item.get("kind") or "document"
        if kind not in _VALID_KINDS:
            kind = "document"
        out.append({"path": path, "kind": kind})
    return out


def parse_doc_context_for_api(raw: list[Any]) -> list[dict[str, str]]:
    """POST /api/chat 的 doc_context：每项须为带合法 kind 的对象。"""
    out: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, str):
            raise DocContextValidationError(
                "doc_context 项须为对象 { path, kind }，不可为字符串"
            )
        if not isinstance(item, dict):
            raise DocContextValidationError("doc_context 项格式无效")
        path = str(item.get("path") or "").strip()
        if not path:
            raise DocContextValidationError("doc_context.path 不能为空")
        kind = item.get("kind")
        if kind not in _VALID_KINDS:
            raise DocContextValidationError(
                f"doc_context.kind 无效: {kind!r}（允许 document、skill_root）"
            )
        out.append({"path": path, "kind": kind})
    return out


def split_doc_context(
    items: list[dict[str, str]],
) -> tuple[list[str], list[str]]:
    docs: list[str] = []
    skills: list[str] = []
    for item in items:
        path = item["path"]
        if item.get("kind") == "skill_root":
            skills.append(path)
        else:
            docs.append(path)
    return docs, skills


def missing_skill_roots(repo: KnowledgeRepo, skill_roots: list[str]) -> list[str]:
    missing: list[str] = []
    for root in skill_roots:
        entry = skill_entry_rel_path(root)
        if not repo.abs_path(entry).is_file():
            missing.append(root)
    return missing
