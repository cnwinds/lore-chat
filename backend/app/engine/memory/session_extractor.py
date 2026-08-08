"""会话级记忆抽取：整段对话（用户为主、助手摘要消歧）→ SlotAction 列表。"""

from __future__ import annotations

from typing import Protocol

from app.engine.memory.normalize import infer_category, match_seed_slot, resolve_slot_key
from app.engine.memory.predicates import seed_prompt_block
from app.engine.memory.prompt_common import (
    NON_DURABLE_IGNORE,
    OWNER_MEMORY_GATE,
    SCOPE_FIDELITY_GATE,
    parse_llm_json_list,
    passes_owner_surface_gate,
)
from app.engine.memory.resolver import SlotAction
from app.engine.secrets import scan_secrets
from app.models.llm import LLMClient

_MAX_DIALOGUE_CHARS = 12000
_MAX_ASSISTANT_CHARS = 280
_MAX_ITEMS = 8

# 兼容旧名
_MAX_USER_CHARS = _MAX_DIALOGUE_CHARS

_SYSTEM_PROMPT = f"""你是用户长期记忆抽取器。在「整段会话定稿」后，只提取关于「知识库主人（当前用户）」的稳定画像。

{OWNER_MEMORY_GATE}

{NON_DURABLE_IGNORE}

{SCOPE_FIDELITY_GATE}

规则：
1. 优先复用「已有槽位」与「种子谓词」；只有必要时才 new 新 slot_key（格式 category.predicate，英文蛇形；禁止把整句原文当 predicate）。
2. action：
   - merge：与已有同槽近义，产出更完整 canonical statement
   - replace：真冲突或用户改口（改为/不再/以后）
   - noop：同义复述且无需改句
   - new：该槽尚不存在
3. statement：第一人称、完整、简洁；整理改写时不得删掉使命题为真的限定语；origin=direct（明确自述）或 inferred（推断）。
4. 输入中的 assistant 行仅供指代消歧与限定语境，不得写成主人画像。
5. 无合适事实时返回空数组。

只输出 JSON：
{{"items":[{{"slot_key":"preference.illustration_style","action":"merge","statement":"我…","category":"preference","origin":"direct","confidence":0.9}}]}}"""


def _normalize_turns(
    messages: list[str] | list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """list[str] 视为纯用户消息；list[tuple[role, text]] 为对话轮次。"""
    turns: list[tuple[str, str]] = []
    for m in messages:
        if isinstance(m, tuple):
            role = (m[0] or "user").strip().lower()
            text = (m[1] or "").strip()
            if role not in ("user", "assistant"):
                continue
        else:
            role = "user"
            text = (m or "").strip()
        if text:
            turns.append((role, text))
    return turns


def _user_texts(turns: list[tuple[str, str]]) -> list[str]:
    return [t for role, t in turns if role == "user"]


class SessionMemoryExtractor(Protocol):
    def extract(
        self,
        messages: list[str] | list[tuple[str, str]],
        *,
        confirmed_summary: list[dict],
    ) -> list[SlotAction]: ...


def _looks_self_narrative(text: str) -> bool:
    """是否像主人自述/偏好指令（用于时间线压缩取舍）。"""
    if passes_owner_surface_gate(text):
        return True
    # 短指令或含第一人称片段但未过完整门禁时，仍优先保留
    return any(k in text for k in ("我", "咱", "偏好", "习惯", "不要", "默认"))


def _clip_text(text: str, max_chars: int, *, keep_tail: bool) -> str:
    """将单段文本压到 max_chars；keep_tail 时保留文末（助手结论常在最后）。"""
    t = text or ""
    if max_chars <= 0:
        return ""
    if len(t) <= max_chars:
        return t
    if max_chars == 1:
        return "…"
    keep = max_chars - 1
    if keep_tail:
        return "…" + t[-keep:].lstrip()
    return t[:keep].rstrip() + "…"


def _truncate_assistant_keep_tail(text: str, max_chars: int) -> str:
    """助手回复关键信息多在文末：超长时保留尾部。"""
    return _clip_text((text or "").strip(), max_chars, keep_tail=True)


def _dedupe_rows(
    rows: list[tuple[int, str, str, bool]],
) -> list[tuple[int, str, str, bool]]:
    seen: set[int] = set()
    out: list[tuple[int, str, str, bool]] = []
    for e in rows:
        if e[0] in seen:
            continue
        seen.add(e[0])
        out.append(e)
    out.sort(key=lambda x: x[0])
    return out


def _user_with_immediate_assistant(
    entries: list[tuple[int, str, str, bool]],
) -> list[tuple[int, str, str, bool]]:
    """仅挂「紧随该用户消息的下一条 assistant」，避免跨轮错挂。"""
    ordered = sorted(entries, key=lambda x: x[0])
    out: list[tuple[int, str, str, bool]] = []
    i = 0
    while i < len(ordered):
        e = ordered[i]
        if e[2] == "user" and e[3]:
            out.append(e)
            if i + 1 < len(ordered) and ordered[i + 1][2] == "assistant":
                out.append(ordered[i + 1])
                i += 2
                continue
        i += 1
    return out


def _pack_head_tail(
    entries: list[tuple[int, str, str, bool]], *, max_chars: int
) -> str:
    """超预算时保留最早/最晚；单行过长则就地截断，避免整段自述消失。"""
    mid_mark_reserve = min(40, max(8, max_chars // 8))
    budget = max(0, max_chars - mid_mark_reserve)
    head_budget = budget // 2
    tail_budget = budget - head_budget

    def _take(
        src: list[tuple[int, str, str, bool]], budget_n: int, *, reverse: bool
    ) -> list[tuple[int, str, str, bool]]:
        rows: list[tuple[int, str, str, bool]] = []
        used = 0
        seq = reversed(src) if reverse else src
        for e in seq:
            prefix = f"[{e[0]}] "
            # 至少留给省略号
            body_budget = budget_n - used - len(prefix) - 1
            if body_budget < 1:
                break
            body = e[1]
            if len(body) > body_budget:
                body = _clip_text(
                    body,
                    body_budget,
                    keep_tail=(e[2] == "assistant"),
                )
            line_len = len(prefix) + len(body) + 1
            if used + line_len > budget_n and rows:
                break
            rows.append((e[0], body, e[2], e[3]))
            used += line_len
        if reverse:
            rows.reverse()
        return rows

    head_rows = _take(entries, head_budget, reverse=False)
    head_ids = {e[0] for e in head_rows}
    rest = [e for e in entries if e[0] not in head_ids]
    tail_rows = _take(rest, tail_budget, reverse=True)

    def _render(rows: list[tuple[int, str, str, bool]]) -> str:
        return "\n".join(f"[{i}] {t}" for i, t, _, _ in rows)

    # 极小预算下 head/tail 可能皆空：强制保留至少一条（优先 user）
    if not head_rows and not tail_rows and entries:
        prefer = next((e for e in entries if e[2] == "user"), entries[0])
        prefix = f"[{prefer[0]}] "
        body_budget = max(1, max_chars - len(prefix))
        body = _clip_text(
            prefer[1],
            body_budget,
            keep_tail=(prefer[2] == "assistant"),
        )
        out = prefix + body
        return out if len(out) <= max_chars else _clip_text(out, max_chars, keep_tail=True)

    kept = {e[0] for e in head_rows + tail_rows}
    # 头尾若碰巧全是助手，把一条被挤掉的用户句塞回（优先中间用户）
    if any(e[2] == "user" for e in entries) and not any(
        e[2] == "user" for e in head_rows + tail_rows
    ):
        omitted_users = [e for e in entries if e[0] not in kept and e[2] == "user"]
        pool = omitted_users or [e for e in entries if e[2] == "user"]
        u = pool[len(pool) // 2]
        body_budget = max(8, max_chars // 3)
        u_body = _clip_text(u[1], body_budget, keep_tail=False)
        u_row = (u[0], u_body, u[2], u[3])
        if head_rows:
            # 替换头段最后一条助手，避免只增不减撑爆预算
            replaced = False
            for i in range(len(head_rows) - 1, -1, -1):
                if head_rows[i][2] == "assistant":
                    head_rows[i] = u_row
                    replaced = True
                    break
            if not replaced:
                head_rows.append(u_row)
        else:
            head_rows = [u_row]
        kept = {e[0] for e in head_rows + tail_rows}

    mid = len(entries) - len(kept)
    if mid > 0:
        out = (
            _render(head_rows)
            + f"\n…(中间约 {mid} 条已压缩)…\n"
            + _render(tail_rows)
        )
    else:
        out = _render(head_rows + tail_rows)
    if len(out) > max_chars:
        out = _clip_text(out, max_chars, keep_tail=True)
    return out


def compress_dialogue_timeline(
    turns: list[tuple[str, str]] | list[str],
    *,
    max_chars: int = _MAX_DIALOGUE_CHARS,
    assistant_max: int = _MAX_ASSISTANT_CHARS,
) -> str:
    """压缩对话时间线：用户尽量完整；助手强截断（保留尾部），仅作消歧（规格 §3 #11）。"""
    if max_chars <= 0:
        return ""
    norm = _normalize_turns(turns)  # type: ignore[arg-type]
    entries: list[tuple[int, str, str, bool]] = []
    for i, (role, text) in enumerate(norm, 1):
        if role == "assistant":
            body = _truncate_assistant_keep_tail(text, assistant_max)
            line = f"assistant: {body}"
            entries.append((i, line, role, True))
        else:
            entries.append((i, text, role, _looks_self_narrative(text)))

    def _render(rows: list[tuple[int, str, str, bool]], *, note: str = "") -> str:
        body = "\n".join(f"[{i}] {t}" for i, t, _, _ in rows)
        return f"{note}{body}" if note else body

    if not entries:
        return ""
    full = _render(entries)
    if len(full) <= max_chars:
        return full

    preferred = [
        e
        for e in entries
        if (e[2] == "user" and e[3]) or e[2] == "assistant"
    ]
    user_narrative = [e for e in entries if e[2] == "user" and e[3]]
    with_nearby_assist = _user_with_immediate_assistant(entries)
    entries_have_user = any(e[2] == "user" for e in entries)

    working = entries
    for candidate, label in (
        (preferred, "对话时间线：优先自述与助手摘要"),
        (with_nearby_assist, "对话时间线：自述 + 邻近助手摘要"),
        (user_narrative, "自述时间线"),
    ):
        if not candidate:
            continue
        rows = _dedupe_rows(candidate)
        # 原对话有用户时，禁止采纳「仅助手」候选，避免用户句被整段抹掉
        if entries_have_user and not any(e[2] == "user" for e in rows):
            continue
        omitted = len(entries) - len(rows)
        note = f"（{label}：保留 {len(rows)} 条，省略 {omitted} 条）\n"
        text = _render(rows, note=note)
        if len(text) <= max_chars:
            return text
        working = rows

    pack_src = working
    if entries_have_user and not any(e[2] == "user" for e in working):
        pack_src = entries
    return _pack_head_tail(pack_src, max_chars=max_chars)


def compress_to_self_timeline(
    messages: list[str], *, max_chars: int = _MAX_DIALOGUE_CHARS
) -> str:
    """兼容：纯用户消息列表 → 对话时间线压缩。"""
    return compress_dialogue_timeline(
        [("user", m) for m in messages],
        max_chars=max_chars,
        assistant_max=_MAX_ASSISTANT_CHARS,
    )


def _compress_messages(
    messages: list[str] | list[tuple[str, str]], *, max_chars: int = _MAX_DIALOGUE_CHARS
) -> str:
    return compress_dialogue_timeline(messages, max_chars=max_chars)


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
        messages: list[str] | list[tuple[str, str]],
        *,
        confirmed_summary: list[dict],
    ) -> list[SlotAction]:
        existing = {f["slot_key"]: f["statement"] for f in confirmed_summary}
        found: dict[str, SlotAction] = {}
        for text in _user_texts(_normalize_turns(messages)):  # type: ignore[arg-type]
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
        messages: list[str] | list[tuple[str, str]],
        *,
        confirmed_summary: list[dict],
    ) -> list[SlotAction]:
        turns = _normalize_turns(messages)  # type: ignore[arg-type]
        if not turns:
            return []
        # 仅跳过含密钥的用户句，勿整段否决同会话其它自述
        safe_turns = [
            (role, text)
            for role, text in turns
            if not (role == "user" and scan_secrets(text))
        ]
        if not any(role == "user" for role, _ in safe_turns):
            return []
        body = _compress_messages(safe_turns)
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
            + "\n\n对话（按时间；assistant 行仅供消歧）：\n"
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
