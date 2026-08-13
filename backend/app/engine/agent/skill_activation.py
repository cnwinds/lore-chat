from __future__ import annotations

_CATALOG_INTRO = """\
[Skill 目录] 用户已跨会话启用下列 Skill。下列仅为 name 与触发条件（description）；\
未命中时不要读取其 SKILL.md。若用户本轮意图命中某条 description，再用 read_doc 读取对应入口全文，\
并按入口指引按需读取 references/ 等子文件；勿预读、勿一次读完整个包。"""

_MULTI_SKILL_RULES = """\
[Skill 冲突总则] 本轮启用了多个 Skill。与用户本条消息冲突时以用户消息为准；\
多个 Skill 之间冲突时合并取交集，无法满足时向用户说明。"""


def build_skill_catalog_system_messages(
    catalog: list[dict[str, str]],
) -> list[dict]:
    """catalog 项含 root / name / description / entry。行为契约只写在本段。"""
    if not catalog:
        return []
    blocks: list[str] = [_CATALOG_INTRO]
    if len(catalog) > 1:
        blocks.append("")
        blocks.append(_MULTI_SKILL_RULES)
    blocks.append("")
    for i, item in enumerate(catalog, start=1):
        blocks.append(
            f"{i}. name: {item['name']}\n"
            f"   description: {item['description']}\n"
            f"   入口: `{item['entry']}`（包根 `{item['root']}`）"
        )
    return [{"role": "system", "content": "\n".join(blocks)}]
