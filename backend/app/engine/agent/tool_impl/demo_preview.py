"""演示环境的工具替换：写类工具只出预览，高风险与按次计费工具直接移除。"""

from __future__ import annotations

from app.engine.agent.tool_catalog import resolve_kb_location

# 移除：SSRF 面（fetch_url）、按次计费（generate_image）、演示站不部署（sandbox_*）、
# 预览价值低于风险（move_entry / delete_kb / write_kb_file）、
# 无归档对象（summarize_conversation：demo 下对话恒为 ephemeral）
DEMO_BLOCKED_TOOLS: frozenset[str] = frozenset(
    {
        "write_kb_file",
        "move_entry",
        "delete_kb",
        "generate_image",
        "fetch_url",
        "summarize_conversation",
        "sandbox_run",
        "sandbox_job_status",
        "sandbox_list_dir",
        "sandbox_read_file",
        "publish_from_sandbox",
        "stage_to_sandbox",
    }
)

# 保留同名同 schema，换成不落盘的预览实现
DEMO_PREVIEW_TOOLS: frozenset[str] = frozenset(
    {
        "write_doc",
        "edit_doc",
        "update_doc_meta",
        "manage_memory",
    }
)

_NOT_PERSISTED = "演示环境未落盘"


def blocked_result(name: str) -> dict:
    return {
        "summary": f"演示环境未提供该工具：{name}",
        "sources": [],
        "error": "demo_tool_unavailable",
        "status": "failed",
    }


def preview_write_doc(args: dict) -> dict:
    rel_path, err = resolve_kb_location(args)
    if err:
        return err
    text = args.get("text") or ""
    if args.get("context"):
        text = f"{args['context']}\n\n{text}"
    return {
        "summary": f"{_NOT_PERSISTED}。真实环境会写入：{rel_path}",
        "sources": [],
        "status": "preview_only",
        "preview": {
            "kind": "doc",
            "path": rel_path,
            "write_mode": args.get("write_mode", "auto"),
            "content": text,
        },
    }


def preview_edit_doc(args: dict) -> dict:
    path = (args.get("path") or "").replace("\\", "/").lstrip("/")
    return {
        "summary": f"{_NOT_PERSISTED}。真实环境会局部编辑：{path}",
        "sources": [],
        "status": "preview_only",
        "preview": {
            "kind": "doc_edit",
            "path": path,
            "edits": args.get("edits") or [],
            "insert": args.get("insert"),
        },
    }


def preview_update_doc_meta(args: dict) -> dict:
    path = (args.get("path") or "").replace("\\", "/").lstrip("/")
    return {
        "summary": f"{_NOT_PERSISTED}。真实环境会更新元数据：{path}",
        "sources": [],
        "status": "preview_only",
        "preview": {"kind": "doc_meta", "path": path, "meta": args.get("meta") or {}},
    }


def preview_manage_memory(args: dict) -> dict:
    action = args.get("action") or "remember"
    content = args.get("content") or ""
    return {
        "summary": f"{_NOT_PERSISTED}。真实环境会记住：{content}",
        "sources": [],
        "status": "preview_only",
        "preview": {"kind": "memory", "action": action, "content": content},
    }


_PREVIEW_HANDLERS = {
    "write_doc": preview_write_doc,
    "edit_doc": preview_edit_doc,
    "update_doc_meta": preview_update_doc_meta,
    "manage_memory": preview_manage_memory,
}


def demo_tool_result(name: str, args: dict) -> dict | None:
    """demo 下的工具结果；返回 None 表示按正常路径执行。"""
    if name in DEMO_BLOCKED_TOOLS:
        return blocked_result(name)
    handler = _PREVIEW_HANDLERS.get(name)
    if handler is not None:
        return handler(args)
    return None
