from __future__ import annotations

from collections.abc import Callable

from app.engine.agent.prompt_parts import tag

_CATALOG_INTRO = """\
【Skill】

已跨会话启用。下列仅为 name、触发条件与包根；未命中不要读取 SKILL.md。
命中后使用渐进式披露原则读取技能。"""

_MULTI_SKILL_RULES = """\
### 冲突

与用户本条消息冲突时以用户消息为准；多个 Skill 之间冲突时合并取交集，无法满足时向用户说明。"""

_ACTIVE_INTRO = """\
【已激活 Skill】

本会话此前已读取下列 SKILL.md。以下是知识库当前正文，直接按它继续，不必再读 SKILL.md；包内其它文件仍按需读取。"""

_SKILL_ENTRY = "SKILL.md"

# 与 llm_history 默认 20 轮窗口同量级：更早的激活不再常驻，需要时由模型重新读取
ACTIVE_SKILL_LOOKBACK = 20
ACTIVE_SKILL_MAX_CHARS = 12000
ACTIVE_SKILL_TOTAL_CHARS = 24000


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
    msg = {"role": "system", "content": "\n".join(blocks)}
    return [tag(msg, "skill_catalog", label="Skill 目录")]


def activated_skill_roots(
    conv: dict,
    catalog: list[dict[str, str]],
    *,
    lookback: int = ACTIVE_SKILL_LOOKBACK,
) -> list[str]:
    """最近 lookback 条助手消息里成功 read_doc 过 `{包根}/SKILL.md`、且仍在启用集的包根。

    最近一次读取的排在前面；工具正文不跨轮回放，这里只认时间线里的读取记录。
    """
    enabled = {
        (item.get("root") or "").strip().strip("/")
        for item in catalog
        if (item.get("root") or "").strip()
    }
    if not enabled:
        return []
    found: list[str] = []
    seen_msgs = 0
    for msg in reversed(conv.get("messages") or []):
        if msg.get("role") != "assistant":
            continue
        seen_msgs += 1
        if seen_msgs > lookback:
            break
        for block in reversed(_tool_blocks(msg.get("timeline"))):
            root = _skill_root_read(block)
            if root and root in enabled and root not in found:
                found.append(root)
    return found


def build_active_skill_messages(
    catalog: list[dict[str, str]],
    roots: list[str],
    read_body: Callable[[str], str],
) -> list[dict]:
    """把已激活包的 SKILL.md 当前正文注入为一条 system 消息；读不到的包跳过。"""
    if not roots:
        return []
    names = {
        (item.get("root") or "").strip().strip("/"): item.get("name") or ""
        for item in catalog
    }
    sections: list[str] = []
    titles: list[str] = []
    budget = ACTIVE_SKILL_TOTAL_CHARS
    for root in roots:
        entry = f"{root}/{_SKILL_ENTRY}"
        try:
            body = (read_body(entry) or "").strip()
        except (FileNotFoundError, OSError, ValueError):
            continue
        if not body:
            continue
        cap = min(ACTIVE_SKILL_MAX_CHARS, budget)
        if cap <= 0:
            break
        if len(body) > cap:
            body = (
                body[:cap]
                + f"\n\n（正文共 {len(body)} 字，此处截至第 {cap} 字；"
                f"其余用 read_doc path={entry} offset={cap} 读取）"
            )
        budget -= min(len(body), cap)
        title = names.get(root) or root
        titles.append(title)
        sections.append(f"### {title} · `{root}`\n\n{body}")
    if not sections:
        return []
    content = _ACTIVE_INTRO + "\n\n" + "\n\n".join(sections)
    msg = {"role": "system", "content": content}
    return [tag(msg, "skill_active", label=f"Skill「{'、'.join(titles)}」")]


def active_skill_system_messages(
    conv: dict | None,
    catalog: list[dict[str, str]],
    repo,
) -> list[dict]:
    if not conv or not catalog or repo is None:
        return []
    roots = activated_skill_roots(conv, catalog)
    return build_active_skill_messages(
        catalog, roots, lambda path: repo.read_doc(path).body
    )


def _tool_blocks(blocks: object) -> list[dict]:
    out: list[dict] = []
    if not isinstance(blocks, list):
        return out
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "parallel":
            out.extend(_tool_blocks(block.get("children")))
        elif block.get("type") == "tool":
            out.append(block)
    return out


def _skill_root_read(block: dict) -> str | None:
    if block.get("tool") != "read_doc" or block.get("status") != "done":
        return None
    if block.get("error"):
        return None
    for src in block.get("sources") or []:
        if not isinstance(src, dict) or src.get("type") != "kb":
            continue
        path = str(src.get("path") or "").replace("\\", "/").strip("/")
        head, _, name = path.rpartition("/")
        if head and name == _SKILL_ENTRY:
            return head
    return None
