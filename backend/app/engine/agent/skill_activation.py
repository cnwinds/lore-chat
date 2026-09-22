from __future__ import annotations

_CATALOG_INTRO = """\
【Skill】

已跨会话启用。下列仅为 name、触发条件与包根；未命中不要读取 SKILL.md。
命中后使用渐进式披露原则读取技能。"""

_MULTI_SKILL_RULES = """\
### 冲突

与用户本条消息冲突时以用户消息为准；多个 Skill 之间冲突时合并取交集，无法满足时向用户说明。"""


def build_skill_catalog_system_messages(
    catalog: list[dict[str, str]],
) -> list[dict]:
    """catalog 项含 root / name / description。入口恒为 `{包根}/SKILL.md`，不逐条重复。"""
    if not catalog:
        return []
    blocks: list[str] = [_CATALOG_INTRO]
    if len(catalog) > 1:
        blocks.append("")
        blocks.append(_MULTI_SKILL_RULES)
    blocks.append("")
    blocks.append("### 目录")
    blocks.append("")
    for i, item in enumerate(catalog, start=1):
        root = (item.get("root") or "").strip()
        blocks.append(f"{i}. **{item['name']}** · `{root}`")
        blocks.append(f"   {item['description']}")
    return [{"role": "system", "content": "\n".join(blocks)}]
