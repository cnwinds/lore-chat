from __future__ import annotations

from typing import Any, Literal

DocContextKind = Literal["document"]

_VALID_KINDS = frozenset({"document"})


class DocContextValidationError(ValueError):
    """聊天请求 doc_context 校验失败。"""


def normalize_doc_context_items(raw: list[Any] | None) -> list[dict[str, str]]:
    """从 DB 读出或兼容旧数据：一律为 document（含历史 skill_root）。"""
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
        out.append({"path": path, "kind": "document"})
    return out


def parse_doc_context_for_api(raw: list[Any]) -> list[dict[str, str]]:
    """POST /api/chat 的 doc_context：每项须为 { path, kind: document }。

    历史客户端若仍传 skill_root，静默降为 document。
    """
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
        if kind == "skill_root":
            kind = "document"
        if kind not in _VALID_KINDS:
            raise DocContextValidationError(
                f"doc_context.kind 无效: {kind!r}（允许 document）"
            )
        out.append({"path": path, "kind": "document"})
    return out


def doc_context_paths(items: list[dict[str, str]]) -> list[str]:
    return [item["path"] for item in items]
