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


__all__ = ["SANDBOX_LOG_TOOLS", "clip_stdout", "display_summary"]
