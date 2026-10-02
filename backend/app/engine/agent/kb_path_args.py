"""写工具参数中的 lore:// 知识库路径规范化。"""

from __future__ import annotations

from typing import Any

from app.engine.context_view.uri import (
    ConversationUri,
    KbUri,
    LegacyConversationRef,
    LoreUri,
    MemoryUri,
    parse,
)
from app.engine.context_view.errors import InvalidUri

# 工具名 → 顶层 KB 路径参数名
_WRITE_TOOL_TOP_LEVEL: dict[str, list[str]] = {
    "write_doc": ["directory"],
    "write_kb_file": ["directory"],
    "edit_doc": ["path"],
    "update_doc_meta": ["path"],
    "move_entry": ["from_path", "to_directory"],
    "delete_kb": ["path"],
    "summarize_conversation": ["directory"],
    "generate_image": ["directory"],
    "publish_from_sandbox": ["directory"],
    "stage_to_sandbox": ["kb_path"],
}

# 数组项内的 KB 路径字段：(数组参数名, 项内字段名)
_WRITE_TOOL_NESTED: dict[str, list[tuple[str, str]]] = {
    "publish_from_sandbox": [("files", "directory")],
    "stage_to_sandbox": [("files", "kb_path")],
}


def _kb_rel_from_uri(parsed: LoreUri | LegacyConversationRef) -> str | None:
    if isinstance(parsed, KbUri):
        p = parsed.rel_path.replace("\\", "/").strip("/")
        return p
    return None


def _read_only_uri_message(raw: str, parsed: LoreUri | LegacyConversationRef) -> dict:
    if isinstance(parsed, LegacyConversationRef) or isinstance(parsed, ConversationUri):
        err = "read_only_uri"
        summary = "只能写知识库路径，不能写会话地址"
    elif isinstance(parsed, MemoryUri):
        err = "read_only_uri"
        summary = "只能写知识库路径，不能写记忆地址"
    else:
        err = "invalid_uri"
        summary = "无法解析为知识库路径"
    return {
        "summary": summary,
        "sources": [],
        "error": err,
        "uri": raw,
    }


def _normalize_kb_path_value(raw: str) -> tuple[str | None, dict | None]:
    text = (raw or "").strip()
    if not text:
        return text, None
    if text.startswith("conversation://"):
        return None, {
            "summary": "只能写知识库路径，不能写会话地址",
            "sources": [],
            "error": "read_only_uri",
            "uri": raw,
        }
    if not text.startswith("lore://"):
        return text, None
    try:
        parsed = parse(text)
    except InvalidUri:
        return None, {
            "summary": "无法解析 lore:// 路径",
            "sources": [],
            "error": "invalid_uri",
            "uri": raw,
        }
    rel = _kb_rel_from_uri(parsed)
    if rel is not None:
        return rel, None
    return None, _read_only_uri_message(raw, parsed)


def normalize_write_tool_args(tool_name: str, args: dict) -> tuple[dict, dict | None]:
    """拷贝 args 并规范化 KB 路径；只读 URI 时返回错误 dict。"""
    spec = _WRITE_TOOL_TOP_LEVEL.get(tool_name)
    nested = _WRITE_TOOL_NESTED.get(tool_name)
    if not spec and not nested:
        return args, None
    out = dict(args)
    for key in spec or []:
        if key not in out:
            continue
        val = out[key]
        if not isinstance(val, str):
            continue
        norm, err = _normalize_kb_path_value(val)
        if err:
            return args, err
        out[key] = norm
    for arr_key, item_key in nested or []:
        items = out.get(arr_key)
        if not isinstance(items, list):
            continue
        new_items: list[Any] = []
        for item in items:
            if not isinstance(item, dict):
                new_items.append(item)
                continue
            item_copy = dict(item)
            if item_key in item_copy and isinstance(item_copy[item_key], str):
                norm, err = _normalize_kb_path_value(item_copy[item_key])
                if err:
                    return args, err
                item_copy[item_key] = norm
            new_items.append(item_copy)
        out[arr_key] = new_items
    return out, None
