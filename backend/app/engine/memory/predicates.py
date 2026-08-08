"""受控记忆谓词（种子表）与别名。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedPredicate:
    slot_key: str
    category: str
    aliases: tuple[str, ...]
    description: str = ""


# 核心种子：半开放词表的稳定底座。别名用于无 LLM 时的启发式对齐。
SEED_PREDICATES: tuple[SeedPredicate, ...] = (
    SeedPredicate(
        "preference.response_language",
        "preference",
        ("默认使用中文", "用中文", "中文交流", "回答用中文", "默认中文"),
        "交流语言",
    ),
    SeedPredicate(
        "preference.response_style",
        "preference",
        ("简短回答", "偏好简洁", "回答简洁", "简洁回答", "简洁直接", "回答直接"),
        "回答风格",
    ),
    SeedPredicate(
        "preference.illustration_style",
        "preference",
        (
            "数据可视化",
            "替代插图",
            "榜单、词云",
            "词云、分布",
            "不用ai生成",
            "不用 ai 生成",
            "不使用ai生成",
            "不使用 ai 生成",
            "ai生成的图片",
            "ai 生成的图片",
            "matplotlib",
        ),
        "配图/可视化偏好",
    ),
    SeedPredicate(
        "preference.cli_preparedness",
        "preference",
        ("提前准备好命令行", "临时查帮助", "命令行", "浪费token", "浪费 token"),
        "工具/CLI 使用偏好",
    ),
    SeedPredicate(
        "workflow.script_layout",
        "workflow",
        ("scripts目录", "scripts 目录", "脚本文件放在", "用法说明则放在"),
        "脚本与文档布局",
    ),
    SeedPredicate(
        "identity.occupation",
        "identity",
        ("我的职业", "工作于", "我是一名", "我是一个"),
        "职业/身份",
    ),
    SeedPredicate(
        "identity.residence",
        "identity",
        ("住在", "住址", "居住"),
        "居住地",
    ),
    SeedPredicate(
        "goal.active_project",
        "goal",
        ("正在做", "长期项目", "目标是"),
        "跨会话持续的方向/主线（非本会话交付清单）",
    ),
    SeedPredicate(
        "constraint.hard_rule",
        "constraint",
        ("不要", "禁止", "不能", "约束"),
        "硬约束",
    ),
    SeedPredicate(
        "preference.time_zone",
        "preference",
        ("时区用", "我的时区", "timezone", "北京时间", "utc+8"),
        "时区偏好",
    ),
    SeedPredicate(
        "preference.detail_level",
        "preference",
        ("详细一点", "多给细节", "讲清楚原理", "不要只给结论"),
        "回答详细度",
    ),
    SeedPredicate(
        "identity.family",
        "identity",
        ("我的孩子", "我家孩子", "我儿子", "我女儿", "我爱人", "我妻子", "我丈夫"),
        "家庭关系",
    ),
    SeedPredicate(
        "workflow.dev_environment",
        "workflow",
        ("我的开发环境", "本地开发环境", "虚拟环境里", "用 conda"),
        "开发/运行环境",
    ),
    SeedPredicate(
        "goal.learning",
        "goal",
        ("正在学", "想学会", "学习目标是"),
        "学习目标",
    ),
    SeedPredicate(
        "project.active_name",
        "project",
        ("项目名叫", "仓库名叫"),
        "活跃项目名",
    ),
)

_BY_SLOT: dict[str, SeedPredicate] = {p.slot_key: p for p in SEED_PREDICATES}


def seed_slot_keys() -> list[str]:
    return [p.slot_key for p in SEED_PREDICATES]


def get_seed(slot_key: str) -> SeedPredicate | None:
    return _BY_SLOT.get(slot_key)


def seed_prompt_block() -> str:
    lines = ["受控种子谓词（优先复用）："]
    for p in SEED_PREDICATES:
        lines.append(f"- {p.slot_key} ({p.category}): {p.description or p.slot_key}")
    return "\n".join(lines)
