"""沙箱命令是否需要用户确认。"""

from __future__ import annotations

import shlex

# 首 token（或前缀）视为只读/低风险，默认可自动执行
_SAFE_FIRST_TOKENS = frozenset({
    "ls", "pwd", "echo", "cat", "head", "tail", "wc", "which", "type",
    "file", "true", "false", "date", "uname", "stat", "basename", "dirname",
    "realpath", "readlink", "test", "[", "printf", "seq", "yes",
})

# 明确高风险：装包、删改系统、提权等 → 始终确认（除非信任模式）
_ALWAYS_CONFIRM_TOKENS = frozenset({
    "apt", "apt-get", "yum", "dnf", "pip", "pip3", "npm", "pnpm", "yarn",
    "rm", "dd", "mkfs", "shutdown", "reboot", "sudo", "su", "chmod", "chown",
    "curl", "wget", "docker", "kill", "pkill", "killall",
})


def command_needs_confirmation(command: str) -> bool:
    """返回 True 表示默认需用户确认后再执行。"""
    text = (command or "").strip()
    if not text:
        return True
    # 链式命令：任一段需要确认则整体确认
    for part in text.replace("||", "&&").split("&&"):
        part = part.strip()
        if not part:
            continue
        if _part_needs_confirm(part):
            return True
    return False


def _part_needs_confirm(part: str) -> bool:
    try:
        tokens = shlex.split(part)
    except ValueError:
        return True
    if not tokens:
        return True
    first = tokens[0]
    if first in _ALWAYS_CONFIRM_TOKENS:
        return True
    if first == "mkdir":
        # mkdir -p 视为可自动；其它 mkdir 也较安全，自动放行
        return False
    if first in _SAFE_FIRST_TOKENS:
        # find 带 -delete/-exec 仍危险
        if first == "find" and any(t in ("-delete", "-exec", "-execdir") for t in tokens):
            return True
        return False
    return True
