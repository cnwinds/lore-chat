"""Git 风格的三路行合并：干净结果可直接落盘；冲突稿只用于展示 / AI，不写进活文件。"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

OURS_LABEL = "当前"
BASE_LABEL = "上次官方"
THEIRS_LABEL = "新官方"

_MARKERS = ("<<<<<<<", "=======", ">>>>>>>", "|||||||")


@dataclass(frozen=True)
class ConflictHunk:
    base: str
    ours: str
    theirs: str

    def as_dict(self) -> dict:
        return {"base": self.base, "ours": self.ours, "theirs": self.theirs}


@dataclass(frozen=True)
class Merge3Result:
    clean: bool
    text: str
    marked: str
    conflicts: list[ConflictHunk]

    def conflicts_as_dicts(self) -> list[dict]:
        return [c.as_dict() for c in self.conflicts]


def has_conflict_markers(text: str) -> bool:
    return any(line.startswith(_MARKERS) for line in text.splitlines())


def _split(text: str) -> list[str]:
    if text == "":
        return []
    return text.splitlines(keepends=True)


def _join(lines: list[str]) -> str:
    return "".join(lines)


def _edits(base: list[str], side: list[str]) -> list[tuple[int, int, int, int]]:
    out: list[tuple[int, int, int, int]] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(
        a=base, b=side, autojunk=False
    ).get_opcodes():
        if tag != "equal":
            out.append((i1, i2, j1, j2))
    return out


def _overlap(a_lo: int, a_hi: int, b_lo: int, b_hi: int) -> bool:
    if a_lo == a_hi and b_lo == b_hi:
        return a_lo == b_lo
    if a_lo == a_hi:
        return b_lo <= a_lo <= b_hi
    if b_lo == b_hi:
        return a_lo <= b_lo <= a_hi
    return a_lo < b_hi and b_lo < a_hi


def _clusters(
    a_edits: list[tuple[int, int, int, int]],
    t_edits: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, bool, bool]]:
    items: list[tuple[int, int, str]] = [("a", e[0], e[1]) for e in a_edits]
    items += [("t", e[0], e[1]) for e in t_edits]
    items.sort(key=lambda x: (x[1], x[2], x[0]))
    if not items:
        return []
    groups: list[tuple[int, int, bool, bool]] = []
    side, lo, hi = items[0]
    saw_a = side == "a"
    saw_t = side == "t"
    for side, elo, ehi in items[1:]:
        if _overlap(lo, hi, elo, ehi):
            lo = min(lo, elo)
            hi = max(hi, ehi)
            saw_a = saw_a or side == "a"
            saw_t = saw_t or side == "t"
            continue
        groups.append((lo, hi, saw_a, saw_t))
        lo, hi, saw_a, saw_t = elo, ehi, side == "a", side == "t"
    groups.append((lo, hi, saw_a, saw_t))
    return groups


def _side_span(base: list[str], side: list[str], blo: int, bhi: int) -> list[str]:
    """`side` 上对应 base[blo:bhi] 的行，含该区间起点的插入；终点插入只在零宽区间计入。"""
    lines: list[str] = []
    zero = blo == bhi
    for tag, i1, i2, j1, j2 in SequenceMatcher(
        a=base, b=side, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            olo, ohi = max(i1, blo), min(i2, bhi)
            if olo < ohi:
                off = j1 + (olo - i1)
                lines.extend(side[off : off + (ohi - olo)])
            continue
        if tag == "delete":
            continue
        if tag == "insert":
            if i1 < blo or i1 > bhi:
                continue
            if i1 == bhi and not zero:
                continue
            lines.extend(side[j1:j2])
            continue
        olo, ohi = max(i1, blo), min(i2, bhi)
        if olo < ohi:
            lines.extend(side[j1:j2])
    return lines


def _marker_lines(hunk: ConflictHunk) -> list[str]:
    return [
        f"<<<<<<< {OURS_LABEL}\n",
        *_split(hunk.ours),
        f"||||||| {BASE_LABEL}\n",
        *_split(hunk.base),
        "=======\n",
        *_split(hunk.theirs),
        f">>>>>>> {THEIRS_LABEL}\n",
    ]


def merge3(base: str, ours: str, theirs: str) -> Merge3Result:
    if ours == theirs:
        return Merge3Result(True, ours, ours, [])
    if ours == base:
        return Merge3Result(True, theirs, theirs, [])
    if theirs == base:
        return Merge3Result(True, ours, ours, [])

    base_lines, ours_lines, theirs_lines = _split(base), _split(ours), _split(theirs)
    clusters = _clusters(_edits(base_lines, ours_lines), _edits(base_lines, theirs_lines))
    out: list[str] = []
    marked: list[str] = []
    conflicts: list[ConflictHunk] = []
    cursor = 0
    for blo, bhi, a_changed, t_changed in clusters:
        equal = base_lines[cursor:blo]
        out.extend(equal)
        marked.extend(equal)
        a_span = _side_span(base_lines, ours_lines, blo, bhi)
        t_span = _side_span(base_lines, theirs_lines, blo, bhi)
        if a_changed and not t_changed:
            out.extend(a_span)
            marked.extend(a_span)
        elif t_changed and not a_changed:
            out.extend(t_span)
            marked.extend(t_span)
        elif a_span == t_span:
            out.extend(a_span)
            marked.extend(a_span)
        else:
            hunk = ConflictHunk(
                _join(base_lines[blo:bhi]),
                _join(a_span),
                _join(t_span),
            )
            conflicts.append(hunk)
            out.extend(a_span)
            marked.extend(_marker_lines(hunk))
        cursor = bhi
    tail = base_lines[cursor:]
    out.extend(tail)
    marked.extend(tail)
    text = _join(out)
    marked_text = _join(marked)
    return Merge3Result(not conflicts, text, marked_text, conflicts)
