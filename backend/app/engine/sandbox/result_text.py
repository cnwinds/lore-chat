"""沙箱命令结果的展示文本。

工具结果里 summary 只写状态，命令输出只在 stdout（模型读到的每段输出只有一份）；
界面卡片、审批后续跑提示需要「状态 + 输出摘录」时在这里拼。
"""

from __future__ import annotations

SANDBOX_LOG_TOOLS = frozenset({"sandbox_run", "sandbox_stop", "sandbox_job_status"})

DISPLAY_MAX_CHARS = 4000
LOG_TAIL_CHARS = 3500
MODEL_STDOUT_MAX_CHARS = 20000
MODEL_STDOUT_HEAD_CHARS = 5000


def clip_stdout(logs: str) -> dict:
    """结果里的 stdout 字段：超长时保留开头与结尾（报错多在末尾），中间注明省略字数。"""
    if len(logs) <= MODEL_STDOUT_MAX_CHARS:
        return {"stdout": logs}
    head = logs[:MODEL_STDOUT_HEAD_CHARS]
    tail = logs[-(MODEL_STDOUT_MAX_CHARS - MODEL_STDOUT_HEAD_CHARS) :]
    omitted = len(logs) - len(head) - len(tail)
    marker = (
        f"\n…（输出过长，中间省略 {omitted} 字；需要完整内容时把输出重定向到 "
        "/workspace 下的文件，再用 sandbox_read_file 读取）…\n"
    )
    return {
        "stdout": head + marker + tail,
        "stdout_total_chars": len(logs),
        "stdout_truncated": True,
    }


def display_summary(out: dict) -> str:
    """状态行 + 输出摘录：已结束取开头，仍在运行或被停止取末尾。"""
    summary = str(out.get("summary") or "")
    logs = str(out.get("stdout") or "").strip()
    if not logs:
        return summary
    if out.get("running") or out.get("stopped"):
        logs = logs[-LOG_TAIL_CHARS:]
    text = f"{summary}\n{logs}" if summary else logs
    return text[:DISPLAY_MAX_CHARS]


def workspace_output_lines(outputs: object) -> list[str]:
    """``workspace_outputs`` → ``- 路径（大小）`` 行；列表被截断时末尾注明。"""
    if not isinstance(outputs, dict):
        return []
    lines: list[str] = []
    for f in outputs.get("files") or []:
        if isinstance(f, dict) and isinstance(f.get("path"), str) and f["path"]:
            lines.append(f"- {f['path']}（{_human_size(f.get('size'))}）")
    if lines and outputs.get("truncated"):
        lines.append("- …（仅列最近修改的部分文件）")
    return lines


def format_workspace_outputs(outputs: object) -> str:
    lines = workspace_output_lines(outputs)
    return "沙箱文件（未入库）：\n" + "\n".join(lines) if lines else ""


def _human_size(size: object) -> str:
    n = size if isinstance(size, int) and size >= 0 else 0
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


__all__ = [
    "SANDBOX_LOG_TOOLS",
    "clip_stdout",
    "display_summary",
    "format_workspace_outputs",
    "workspace_output_lines",
]
