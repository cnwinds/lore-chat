"""沙箱命令预处理：保证 stdout 可流式观测。"""

from __future__ import annotations

import re

_PYTHON_INVOCATION = re.compile(
    r"(?:^|[\s;&|(])(python3?(?:\.\d+)?|/.+/python\d*)(?=\s|$)",
    re.IGNORECASE,
)
_PYTHON_UNBUFFER_FLAG = re.compile(r"python\d*(?:\.\d+)?\s+-u\b", re.IGNORECASE)


def prepare_streaming_command(command: str) -> str:
    """为 Python 命令注入 unbuffer，避免 job 轮询 / 伪 TTY 下块缓冲拖到最后才出日志。"""
    cmd = (command or "").strip()
    if not cmd:
        return cmd
    upper = cmd.upper()
    if "PYTHONUNBUFFERED=1" in upper or "PYTHONUNBUFFERED=TRUE" in upper:
        return cmd
    if _PYTHON_UNBUFFER_FLAG.search(cmd):
        return cmd
    if _PYTHON_INVOCATION.search(cmd):
        return f"PYTHONUNBUFFERED=1 {cmd}"
    return cmd
