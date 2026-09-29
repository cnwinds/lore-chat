"""人设文本 diff、编辑计划与应用（纯函数）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable

_WS_FOLD = re.compile(r"\s+")


@dataclass(frozen=True)
class OwnerChanges:
    protected_spans: list[tuple[int, int]]
    added_texts: list[str]
    removed_texts: list[str]


def _line_starts(text: str) -> list[int]:
    lines = text.splitlines(keepends=True)
    starts: list[int] = []
    pos = 0
    for ln in lines:
        starts.append(pos)
        pos += len(ln)
    return starts


def owner_changes(base: str, current: str) -> OwnerChanges:
    base_lines = base.splitlines(keepends=True)
    cur_lines = current.splitlines(keepends=True)
    if not base_lines and not cur_lines:
        return OwnerChanges([], [], [])

    cur_starts = _line_starts(current)
    cur_len = len(current)

    protected: list[tuple[int, int]] = []
    added: list[str] = []
    removed: list[str] = []

    for tag, i1, i2, j1, j2 in SequenceMatcher(
        a=base_lines, b=cur_lines, autojunk=False
    ).get_opcodes():
        if tag in ("replace", "insert") and j2 > j1:
            start = cur_starts[j1] if j1 < len(cur_starts) else cur_len
            end = cur_starts[j2] if j2 < len(cur_starts) else cur_len
            protected.append((start, end))
            block = "".join(cur_lines[j1:j2])
            if block.strip():
                added.append(block)
        if tag in ("replace", "delete") and i2 > i1:
            block = "".join(base_lines[i1:i2])
            if block.strip():
                removed.append(block)

    return OwnerChanges(protected, added, removed)


@dataclass(frozen=True)
class PersonaEdit:
    op: str
    find: str
    after: str
    text: str
    card_refs: tuple[str, ...]
    memory_refs: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class EditPlan:
    applied: list[PersonaEdit]
    body: str
    dropped: list[dict]


@dataclass(frozen=True)
class _PlannedEdit:
    """校验阶段在 original 上算好的位置；应用阶段只切片，不再搜索。"""

    edit: PersonaEdit
    mode: str  # replace | delete | insert | append
    start: int
    end: int


def _fold_ws(text: str) -> str:
    return _WS_FOLD.sub(" ", (text or "")).strip()


def _find_unique(haystack: str, needle: str) -> tuple[int, int] | None:
    if needle == "":
        return None
    hits: list[int] = []
    start = 0
    while True:
        i = haystack.find(needle, start)
        if i < 0:
            break
        hits.append(i)
        start = i + max(1, len(needle))
    if len(hits) == 1:
        return hits[0], len(needle)
    if len(hits) > 1:
        return None
    stripped = needle.strip()
    if not stripped or stripped == needle:
        return None
    hits = []
    start = 0
    while True:
        i = haystack.find(stripped, start)
        if i < 0:
            break
        hits.append(i)
        start = i + max(1, len(stripped))
    if len(hits) == 1:
        return hits[0], len(stripped)
    return None


def _find_all_count(haystack: str, needle: str) -> int:
    if not needle:
        return 0
    n = 0
    start = 0
    while True:
        i = haystack.find(needle, start)
        if i < 0:
            break
        n += 1
        start = i + max(1, len(needle))
    return n


def _spans_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _point_in_span(point: int, span: tuple[int, int]) -> bool:
    return span[0] <= point < span[1]


def _tombstoned(text: str, negative_texts: list[str]) -> bool:
    text_n = _fold_ws(text)
    for raw in negative_texts:
        neg = _fold_ws(raw)
        if len(neg) < 4:
            continue
        if len(neg) >= 8 and neg in text_n:
            return True
        if SequenceMatcher(None, text_n, neg).ratio() >= 0.6:
            return True
    return False


def _delete_span_on_current(current: str, start: int, end: int) -> tuple[int, int]:
    line_start = current.rfind("\n", 0, start) + 1
    tail = end
    line_end = current.find("\n", tail)
    at_line_end = line_end < 0 or tail == line_end
    at_line_start = start == line_start
    if at_line_start and at_line_end:
        if line_end >= 0:
            return line_start, line_end + 1
        return line_start, len(current)
    return start, end


def _resolve_edit(
    op: str, current: str, find: str, after: str, text: str
) -> tuple[_PlannedEdit | None, tuple[int, int] | None, int | None, str | None]:
    """返回 (planned, span_for_overlap, insert_point, error)。"""
    edit_stub = PersonaEdit(
        op=op,
        find=find,
        after=after,
        text=text,
        card_refs=(),
        memory_refs=(),
        reason="",
    )
    if op == "insert":
        tail = len(current.rstrip())
        if not after.strip():
            return _PlannedEdit(edit_stub, "append", tail, tail), None, tail, None
        loc = _find_unique(current, after)
        if loc is None:
            probe = _find_all_count(current, after)
            if probe == 0:
                return None, None, None, "not_found"
            return None, None, None, "ambiguous"
        anchor_end = loc[0] + loc[1]
        nl = current.find("\n", anchor_end)
        point = nl if nl >= 0 else len(current)
        if point >= tail:
            # 锚在最后一行等同追加：与其他追加按给出顺序拼接，而不是互相判重叠。
            return _PlannedEdit(edit_stub, "append", tail, tail), None, tail, None
        return (
            _PlannedEdit(edit_stub, "insert", point, point),
            None,
            point,
            None,
        )

    loc = _find_unique(current, find)
    if loc is None:
        if find.strip() == "":
            return None, None, None, "missing_text"
        probe = _find_all_count(current, find)
        if probe == 0:
            return None, None, None, "not_found"
        return None, None, None, "ambiguous"
    start, length = loc
    end = start + length
    if op == "replace":
        return (
            _PlannedEdit(edit_stub, "replace", start, end),
            (start, end),
            None,
            None,
        )
    d_start, d_end = _delete_span_on_current(current, start, end)
    return (
        _PlannedEdit(edit_stub, "delete", d_start, d_end),
        (d_start, d_end),
        None,
        None,
    )


def _apply_planned(original: str, plans: list[_PlannedEdit]) -> str:
    body = original
    others = [(p.start, i, p) for i, p in enumerate(plans) if p.mode != "append"]
    for _, _, p in sorted(others, key=lambda x: (x[0], x[1]), reverse=True):
        ed = p.edit
        if p.mode == "replace":
            body = body[: p.start] + ed.text.strip("\n") + body[p.end :]
        elif p.mode == "delete":
            body = body[: p.start] + body[p.end :]
        elif p.mode == "insert":
            t = ed.text.strip("\n")
            body = body[: p.start] + "\n" + t + body[p.start :]

    appends = [p.edit.text.strip("\n") for p in plans if p.mode == "append"]
    if appends:
        tail = len(body.rstrip())
        lead = "\n" if body[:tail].strip() else ""
        body = body[:tail] + lead + "\n".join(appends) + body[tail:]
    return body


def _split_basis(
    basis: list[str], card_refs: set[str], memory_refs: set[str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    cards: list[str] = []
    mems: list[str] = []
    for ref in basis:
        if ref in memory_refs:
            mems.append(ref)
        else:
            cards.append(ref)
    return tuple(cards), tuple(mems)


def plan_edits(
    current: str,
    raw_edits: list,
    *,
    card_refs: set[str],
    memory_refs: set[str],
    protected_spans: list[tuple[int, int]],
    negative_texts: list[str],
    secret_scan: Callable[[str], bool],
    max_edits: int = 8,
    text_max_chars: int = 600,
    max_total_chars: int = 6000,
    max_growth_chars: int = 1200,
) -> EditPlan:
    accepted: list[tuple[int, _PlannedEdit]] = []
    accepted_spans: list[tuple[int, int]] = []
    accepted_points: list[int] = []
    dropped: list[dict] = []

    for index, raw in enumerate(raw_edits):
        if index >= max_edits:
            dropped.append({"index": index, "reason": "bad_op"})
            continue
        if not isinstance(raw, dict):
            dropped.append({"index": index, "reason": "bad_op"})
            continue
        op = raw.get("op")
        if op not in ("replace", "insert", "delete"):
            dropped.append({"index": index, "reason": "bad_op"})
            continue

        find = str(raw.get("find") or "")
        after = str(raw.get("after") or "")
        text = str(raw.get("text") or "")
        reason = str(raw.get("reason") or "")

        if op in ("replace", "insert") and not text.strip():
            dropped.append({"index": index, "reason": "missing_text"})
            continue
        if op in ("replace", "delete") and not find.strip():
            dropped.append({"index": index, "reason": "missing_text"})
            continue
        if op in ("replace", "insert") and len(text) > text_max_chars:
            dropped.append({"index": index, "reason": "text_too_long"})
            continue

        basis_raw = raw.get("basis")
        if not basis_raw or not isinstance(basis_raw, list):
            dropped.append({"index": index, "reason": "no_basis"})
            continue
        basis = [str(x) for x in basis_raw]
        allowed = card_refs | memory_refs
        if any(b not in allowed for b in basis):
            dropped.append({"index": index, "reason": "bad_basis"})
            continue
        card_t, mem_t = _split_basis(basis, card_refs, memory_refs)
        if mem_t and op != "delete":
            dropped.append({"index": index, "reason": "memory_basis_not_delete"})
            continue
        if op in ("replace", "insert") and not card_t:
            dropped.append({"index": index, "reason": "memory_basis_not_delete"})
            continue

        planned, span, point, loc_err = _resolve_edit(
            op, current, find, after, text
        )
        if loc_err or planned is None:
            dropped.append({"index": index, "reason": loc_err or "not_found"})
            continue

        if op in ("replace", "delete") and span:
            if any(_spans_overlap(span, prot) for prot in protected_spans):
                dropped.append({"index": index, "reason": "protected"})
                continue

        if op in ("replace", "insert") and _tombstoned(text, negative_texts):
            dropped.append({"index": index, "reason": "tombstoned"})
            continue
        if op in ("replace", "insert") and secret_scan(text):
            dropped.append({"index": index, "reason": "secret"})
            continue

        if span and any(_spans_overlap(span, s) for s in accepted_spans):
            dropped.append({"index": index, "reason": "overlap"})
            continue
        if span and any(_point_in_span(p, span) for p in accepted_points):
            dropped.append({"index": index, "reason": "overlap"})
            continue
        if point is not None:
            if any(_point_in_span(point, s) for s in accepted_spans):
                dropped.append({"index": index, "reason": "overlap"})
                continue
            if planned.mode != "append" and any(
                p == point for p in accepted_points
            ):
                dropped.append({"index": index, "reason": "overlap"})
                continue

        trial_edit = PersonaEdit(
            op=op,
            find=find,
            after=after,
            text=text,
            card_refs=card_t,
            memory_refs=mem_t,
            reason=reason,
        )
        trial_planned = _PlannedEdit(
            edit=trial_edit,
            mode=planned.mode,
            start=planned.start,
            end=planned.end,
        )
        trial_body = _apply_planned(
            current, [p for _, p in accepted] + [trial_planned]
        )
        growth = len(trial_body) - len(current)
        if growth > max_growth_chars:
            dropped.append({"index": index, "reason": "growth_cap"})
            continue
        if len(trial_body) > max_total_chars:
            dropped.append({"index": index, "reason": "total_cap"})
            continue

        accepted.append((index, trial_planned))
        if span:
            accepted_spans.append(span)
        if point is not None:
            accepted_points.append(point)

    if not accepted:
        return EditPlan([], current, dropped)

    plans = [p for _, p in accepted]
    body = _apply_planned(current, plans)
    if current.strip() and not body.strip():
        for idx, _ in accepted:
            dropped.append({"index": idx, "reason": "would_empty"})
        return EditPlan([], current, dropped)

    if body == current:
        return EditPlan([], current, dropped)

    edits_only = [p.edit for p in plans]
    return EditPlan(edits_only, body, dropped)


def texts_to_spans(current: str, texts: list[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for raw in texts:
        needle = raw.strip()
        if len(needle) < 4:
            continue
        start = 0
        while True:
            i = current.find(needle, start)
            if i < 0:
                break
            spans.append((i, i + len(needle)))
            start = i + max(1, len(needle))
    return spans
