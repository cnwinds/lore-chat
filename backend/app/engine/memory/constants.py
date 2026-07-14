from __future__ import annotations

MEMORY_DOC_REL = "系统/记忆.md"

ORIGIN_RANK = {
    "inferred": 0,
    "direct": 1,
    "explicit_remember": 2,
    "manual": 3,
}

CATEGORIES = frozenset(
    {"identity", "preference", "goal", "project", "workflow", "constraint"}
)

SECTION_BY_CATEGORY: dict[str, str] = {
    "identity": "身份与稳定背景",
    "preference": "偏好与沟通方式",
    "goal": "长期目标与正在做的事",
    "project": "长期目标与正在做的事",
    "workflow": "工作方式与工具环境",
    "constraint": "关键约束",
}

DEFAULT_MEMORY_MAX_CHARS = 4000
