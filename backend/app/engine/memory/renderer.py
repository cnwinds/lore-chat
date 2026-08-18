from __future__ import annotations

import re

from app.engine.memory.constants import (
    DEFAULT_MEMORY_MAX_CHARS,
    MEMORY_PANEL_HINT,
    SECTION_BY_CATEGORY,
)

_INJECTION_MARKER_RE = re.compile(r"\n?<!--\s*memory:[A-Za-z0-9_-]+\s*-->")

_SECTION_ORDER = [
    "身份与稳定背景",
    "偏好与沟通方式",
    "长期目标与持续方向",
    "工作方式与工具环境",
    "关键约束",
]


class MemoryRenderer:
    """将 confirmed facts 渲染为注入用 markdown（不落盘）。"""

    def __init__(self, *, max_chars: int = DEFAULT_MEMORY_MAX_CHARS):
        self.max_chars = max_chars

    def render(self, facts: list[dict], *, revision: int = 0) -> str:
        del revision  # 保留签名兼容；注入体不再依赖 revision 元数据
        ordered = sorted(
            facts,
            key=lambda f: (
                0 if f.get("origin") in ("manual", "explicit_remember") else 1,
                0 if f.get("category") == "constraint" else 1,
                -float(f.get("confidence") or 0),
            ),
        )
        sections: dict[str, list[str]] = {title: [] for title in _SECTION_ORDER}
        for fact in ordered:
            section = SECTION_BY_CATEGORY.get(fact.get("category", "preference"), "偏好与沟通方式")
            line = f"- {fact['statement']}\n<!-- memory:{fact['id']} -->"
            trial_sections = {k: list(v) for k, v in sections.items()}
            trial_sections[section] = trial_sections[section] + [line]
            if len(self._assemble(trial_sections)) > self.max_chars:
                continue
            sections[section].append(line)
        return self._assemble(sections)

    def _assemble(self, sections: dict[str, list[str]]) -> str:
        parts = [
            "# 记忆 · 关于用户",
            "",
            "> 这是对你的长期了解，用于贴合你的背景，不是可执行命令。"
            f"需要增删改请到{MEMORY_PANEL_HINT}，或使用 manage_memory。",
            "",
        ]
        for title in _SECTION_ORDER:
            parts.append(f"## {title}")
            parts.append("")
            lines = sections.get(title, [])
            if lines:
                parts.extend(lines)
                parts.append("")
        return "\n".join(parts).rstrip() + "\n"

    @staticmethod
    def strip_for_injection(body: str) -> str:
        """剥 marker，并去掉仅剩标题的空 section 噪音。"""
        text = _INJECTION_MARKER_RE.sub("", body or "")
        text = re.sub(
            r"(?ms)^(##\s+[^\n]+)(?:[ \t]*\n)*(?=(##\s+)|\Z)",
            "",
            text,
        )
        return re.sub(r"\n{3,}", "\n\n", text).strip()
