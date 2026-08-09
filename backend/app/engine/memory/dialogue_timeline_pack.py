"""对话时间线压缩：预算 / 头尾 / 用户保真（会话级记忆抽取输入）。"""

from __future__ import annotations

from app.engine.memory.prompt_common import passes_owner_surface_gate

_MAX_DIALOGUE_CHARS = 12000
_MAX_ASSISTANT_CHARS = 280
# 兼容旧名
_MAX_USER_CHARS = _MAX_DIALOGUE_CHARS

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


def _looks_self_narrative(text: str) -> bool:
    """是否像主人自述（与写入表面门禁同一判定，供时间线压缩取舍）。"""
    return passes_owner_surface_gate(text)


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


