"""演示环境的工具替换：写类工具只出预览，高风险与按次计费工具直接移除。"""

from __future__ import annotations

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
