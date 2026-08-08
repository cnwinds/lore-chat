"""会话级记忆抽取：整段用户消息 → SlotAction 列表。"""

from __future__ import annotations

from typing import Protocol

from app.engine.memory.normalize import infer_category, match_seed_slot, resolve_slot_key
from app.engine.memory.predicates import seed_prompt_block
from app.engine.memory.prompt_common import (
    NON_DURABLE_IGNORE,
    OWNER_MEMORY_GATE,
    parse_llm_json_list,
    passes_owner_surface_gate,
)
from app.engine.memory.resolver import SlotAction
from app.engine.secrets import scan_secrets
from app.models.llm import LLMClient

_MAX_USER_CHARS = 12000
_MAX_ITEMS = 8

_SYSTEM_PROMPT = f"""你是用户长期记忆抽取器。在「整段会话定稿」后，只提取关于「知识库主人（当前用户）」的稳定画像。

{OWNER_MEMORY_GATE}

{NON_DURABLE_IGNORE}

规则：
1. 优先复用「已有槽位」与「种子谓词」；只有必要时才 new 新 slot_key（格式 category.predicate，英文蛇形；禁止把整句原文当 predicate）。
2. action：
   - merge：与已有同槽近义，产出更完整 canonical statement
   - replace：真冲突或用户改口（改为/不再/以后）
   - noop：同义复述且无需改句
   - new：该槽尚不存在
3. statement：第一人称、完整、简洁；origin=direct（明确自述）或 inferred（推断）。
4. 无合适事实时返回空数组。

只输出 JSON：
{{"items":[{{"slot_key":"preference.illustration_style","action":"merge","statement":"我…","category":"preference","origin":"direct","confidence":0.9}}]}}"""


class SessionMemoryExtractor(Protocol):
    def extract(
        self,
        user_messages: list[str],
        *,
        confirmed_summary: list[dict],
    ) -> list[SlotAction]: ...


def _looks_self_narrative(text: str) -> bool:
    """是否像主人自述/偏好指令（用于时间线压缩取舍）。"""
    if passes_owner_surface_gate(text):
        return True
    # 短指令或含第一人称片段但未过完整门禁时，仍优先保留
    return any(k in text for k in ("我", "咱", "偏好", "习惯", "不要", "默认"))


def compress_to_self_timeline(
    messages: list[str], *, max_chars: int = _MAX_USER_CHARS
) -> str:
    """将用户消息压成按时间排列的自述时间线（规格 §3 #11 / §6.3）。"""
    entries: list[tuple[int, str, bool]] = []
    for i, m in enumerate(messages, 1):
        t = (m or "").strip()
        if not t:
            continue
        entries.append((i, t, _looks_self_narrative(t)))

    def _render(rows: list[tuple[int, str, bool]], *, note: str = "") -> str:
        body = "\n".join(f"[{i}] {t}" for i, t, _ in rows)
        return f"{note}{body}" if note else body

    if not entries:
        return ""
    full = _render(entries)
    if len(full) <= max_chars:
        return full

    # 优先保留自述/偏好；注明省略条数
    narrative = [e for e in entries if e[2]]
    omitted = len(entries) - len(narrative)
    if narrative:
        note = f"（自述时间线：保留 {len(narrative)} 条自述，省略 {omitted} 条非自述）\n"
        text = _render(narrative, note=note)
        if len(text) <= max_chars:
            return text
        entries = narrative
        full = text

    # 仍超长：保留最早与最晚各一半预算，中间标省略
    budget = max_chars - 40
    head_budget = budget // 2
    tail_budget = budget - head_budget
    head_rows: list[tuple[int, str, bool]] = []
    tail_rows: list[tuple[int, str, bool]] = []
    used = 0
    for e in entries:
        line = f"[{e[0]}] {e[1]}\n"
        if used + len(line) > head_budget:
            break
        head_rows.append(e)
        used += len(line)
    used = 0
    for e in reversed(entries):
        if e in head_rows:
            break
        line = f"[{e[0]}] {e[1]}\n"
        if used + len(line) > tail_budget:
            break
        tail_rows.append(e)
        used += len(line)
    tail_rows.reverse()
    kept = {e[0] for e in head_rows + tail_rows}
    mid = len(entries) - len(kept)
    return (
        _render(head_rows)
        + f"\n…(中间约 {mid} 条自述已压缩)…\n"
        + _render(tail_rows)
    )


def _compress_user_messages(messages: list[str], *, max_chars: int = _MAX_USER_CHARS) -> str:
    return compress_to_self_timeline(messages, max_chars=max_chars)


def _to_action(
    *,
    statement: str,
    slot: str,
    category: str,
    action: str,
    origin: str,
    confidence: float,
) -> SlotAction:
    return SlotAction(
        slot_key=slot,
        action=action,
        statement=statement,
        category=category,
        origin=origin,
        confidence=max(0.0, min(1.0, confidence)),
    )


class RuleBasedSessionExtractor:
    """无 LLM：按种子别名从用户消息启发式抽 direct 事实。"""

    def extract(
        self,
        user_messages: list[str],
        *,
        confirmed_summary: list[dict],
    ) -> list[SlotAction]:
        existing = {f["slot_key"]: f["statement"] for f in confirmed_summary}
        found: dict[str, SlotAction] = {}
        for msg in user_messages:
            text = (msg or "").strip()
            if len(text) < 4 or scan_secrets(text):
                continue
            slot = match_seed_slot(text)
            if not slot:
                continue
            cat = infer_category(text)
            stmt = text if len(text) <= 200 else text[:200].rstrip() + "…"
            if not passes_owner_surface_gate(stmt, slot_key=slot):
                continue
            action = "merge" if slot in existing else "new"
            found[slot] = _to_action(
                statement=stmt,
                slot=slot,
                category=cat,
                action=action,
                origin="direct",
                confidence=0.9,
            )
            existing[slot] = stmt
        return list(found.values())[:_MAX_ITEMS]


class LLMSessionExtractor:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def extract(
        self,
        user_messages: list[str],
        *,
        confirmed_summary: list[dict],
    ) -> list[SlotAction]:
        if not user_messages:
            return []
        body = _compress_user_messages(user_messages)
        if scan_secrets(body):
            return []
        confirmed_lines = []
        for f in confirmed_summary[:40]:
            confirmed_lines.append(f"- {f.get('slot_key')}: {f.get('statement')}")
        confirmed_block = (
            "已确认画像（请对齐合并）：\n" + "\n".join(confirmed_lines)
            if confirmed_lines
            else "已确认画像：空"
        )
        user_content = (
            seed_prompt_block()
            + "\n\n"
            + confirmed_block
            + "\n\n用户消息（按时间）：\n"
            + body
        )
        raw = self.llm.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            big=False,
            temperature=0.1,
        ).strip()
        items = parse_llm_json_list(raw, key="items")[:_MAX_ITEMS]
        # 长句优先，便于同批近义对齐到同一 topic_/种子
        items.sort(key=lambda x: len(str(x.get("statement") or "")), reverse=True)
        batch_existing = [
            {
                "slot_key": f.get("slot_key"),
                "statement": f.get("statement"),
                "category": f.get("category"),
            }
            for f in confirmed_summary
        ]
        actions: list[SlotAction] = []
        for item in items:
            statement = str(item.get("statement", "")).strip()
            if len(statement) < 3 or scan_secrets(statement):
                continue
            if not passes_owner_surface_gate(statement):
                continue
            slot_raw = str(item.get("slot_key") or "").strip()
            category = str(item.get("category") or infer_category(statement)).strip()
            slot = resolve_slot_key(
                category,
                statement,
                slot_hint=slot_raw,
                existing=batch_existing,
            )
            action = str(item.get("action") or "new").strip().lower()
            if action not in ("merge", "replace", "noop", "new"):
                action = "new"
            origin = str(item.get("origin") or "direct").strip()
            if origin not in ("direct", "inferred"):
                origin = "direct"
            try:
                confidence = float(item.get("confidence", 0.9))
            except (TypeError, ValueError):
                confidence = 0.9
            actions.append(
                _to_action(
                    statement=statement,
                    slot=slot,
                    category=category,
                    action=action,
                    origin=origin,
                    confidence=confidence,
                )
            )
            batch_existing.append(
                {
                    "slot_key": slot,
                    "statement": statement,
                    "category": category,
                }
            )
        return actions
