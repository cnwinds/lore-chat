from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Edit:
    old_string: str
    new_string: str
    replace_all: bool = False


@dataclass
class PatchError:
    code: str
    message: str
    hint: str | None = None
    occurrences: list[dict] | None = None
    suggestion: str | None = None


@dataclass
class PatchResult:
    ok: bool
    body: str | None
    applied: int
    message: str
    error: PatchError | None = None
    preview: str | None = None
    affected_start: int | None = None
    affected_end: int | None = None


def _context_snippet(body: str, start: int, length: int, *, radius: int = 50) -> str:
    lo = max(0, start - radius)
    hi = min(len(body), start + length + radius)
    return body[lo:hi]


def _find_exact(body: str, needle: str) -> list[int]:
    if not needle:
        return []
    out: list[int] = []
    i = 0
    while True:
        j = body.find(needle, i)
        if j < 0:
            break
        out.append(j)
        i = j + 1
    return out


def _fail_not_found(body: str, needle: str) -> PatchResult:
    return PatchResult(
        ok=False,
        body=None,
        applied=0,
        message="old_string 在文档中未找到",
        error=PatchError(
            code="NOT_FOUND",
            message="old_string 在文档中未找到",
            hint=_context_snippet(body, 0, min(len(needle), len(body))),
            suggestion="请用 read_doc 重新读取后复制精确文本",
        ),
    )


def _fail_ambiguous(body: str, needle: str, positions: list[int]) -> PatchResult:
    return PatchResult(
        ok=False,
        body=None,
        applied=0,
        message=f"old_string 在文档中出现 {len(positions)} 次",
        error=PatchError(
            code="AMBIGUOUS",
            message=f"old_string 在文档中出现 {len(positions)} 次",
            occurrences=[
                {
                    "offset": pos,
                    "context": _context_snippet(body, pos, len(needle)),
                }
                for pos in positions
            ],
            suggestion="请扩大 old_string 范围，包含更多唯一上下文",
        ),
    )


def _make_preview(body: str, start: int, old_len: int, new_len: int) -> str:
    return _context_snippet(body, start, max(old_len, new_len), radius=80)


def _current_to_original(
    pos: int, mutations: list[tuple[int, int, int]]
) -> int:
    """Map position in current body to original body coordinates."""
    offset = 0
    for orig_start, orig_end, new_len in mutations:
        old_len = orig_end - orig_start
        cur_start = orig_start + offset
        cur_end = cur_start + old_len
        if pos < cur_start:
            return pos - offset
        if pos >= cur_end:
            offset += new_len - old_len
            continue
        return orig_start
    return pos - offset


def apply_edits(body: str, edits: list[Edit], *, max_patch_chars: int) -> PatchResult:
    if not edits:
        return PatchResult(
            ok=False,
            body=None,
            applied=0,
            message="edits 不能为空",
            error=PatchError(code="INVALID", message="edits 不能为空"),
        )

    current = body
    applied = 0
    last_preview: str | None = None
    mutations: list[tuple[int, int, int]] = []
    affected_starts: list[int] = []
    affected_ends: list[int] = []

    for edit in edits:
        if len(edit.old_string) > max_patch_chars or len(edit.new_string) > max_patch_chars:
            return PatchResult(
                ok=False,
                body=None,
                applied=applied,
                message="单段 old_string 或 new_string 超出长度限制",
                error=PatchError(
                    code="TOO_LARGE",
                    message="单段 old_string 或 new_string 超出长度限制",
                ),
            )

        positions = _find_exact(current, edit.old_string)
        if not positions:
            return _fail_not_found(current, edit.old_string)

        if len(positions) > 1 and not edit.replace_all:
            return _fail_ambiguous(current, edit.old_string, positions)

        if edit.replace_all:
            n = len(edit.old_string)
            spans = [(pos, pos + n) for pos in positions]
            for start, end in reversed(spans):
                orig_start = _current_to_original(start, mutations)
                orig_end = _current_to_original(end, mutations)
                affected_starts.append(orig_start)
                affected_ends.append(orig_end)
                mutations.append((orig_start, orig_end, len(edit.new_string)))
                current = current[:start] + edit.new_string + current[end:]
            last_preview = _make_preview(
                current, spans[0][0], spans[0][1] - spans[0][0], len(edit.new_string)
            )
        else:
            pos = positions[0]
            end = pos + len(edit.old_string)
            orig_start = _current_to_original(pos, mutations)
            orig_end = _current_to_original(end, mutations)
            affected_starts.append(orig_start)
            affected_ends.append(orig_end)
            mutations.append((orig_start, orig_end, len(edit.new_string)))
            current = current[:pos] + edit.new_string + current[end:]
            last_preview = _make_preview(
                current, pos, end - pos, len(edit.new_string)
            )
        applied += 1

    delta = len(current) - len(body)
    sign = f"+{delta}" if delta >= 0 else str(delta)
    return PatchResult(
        ok=True,
        body=current,
        applied=applied,
        message=f"已应用 {applied} 处修改（{sign} 字）",
        preview=last_preview,
        affected_start=min(affected_starts) if affected_starts else None,
        affected_end=max(affected_ends) if affected_ends else None,
    )
