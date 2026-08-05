from __future__ import annotations

from app.engine.kb_skill import build_skill_activation_body
from app.storage.repo import KnowledgeRepo

_MULTI_SKILL_RULES = """\
[Skill 冲突总则] 本轮附加了多个 Skill。与用户本条消息冲突时以用户消息为准；多个 Skill 之间冲突时合并取交集，无法满足时向用户说明。"""


def build_skill_activation_system_messages(
    repo: KnowledgeRepo,
    skill_roots: list[str],
    *,
    disclosure_limit: int,
) -> list[dict]:
    if not skill_roots:
        return []
    messages: list[dict] = []
    if len(skill_roots) > 1:
        messages.append({"role": "system", "content": _MULTI_SKILL_RULES})
    for root in skill_roots:
        built = build_skill_activation_body(repo, root, limit=disclosure_limit)
        if built is None:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"[Skill 激活失败] `{root or '(根目录)'}`："
                        "未找到 SKILL.md，请从托盘移除后重试。"
                    ),
                }
            )
            continue
        entry, text = built
        label = root or "(根目录)"
        messages.append(
            {
                "role": "system",
                "content": (
                    f"[Skill 激活] `{label}`\n"
                    f"入口文件: `{entry}`\n"
                    f"以下仅注入入口正文；引用文件须按入口指引用 read_doc 按需读取。\n\n"
                    f"{text}"
                ),
            }
        )
    return messages
