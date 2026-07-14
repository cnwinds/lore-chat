from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MessageChunk:
    index: int
    start_char: int
    end_char: int
    text: str
    offset_version: str = "unicode-codepoint-v1"


def chunk_message(text: str, *, size: int = 1000, overlap: int = 150) -> list[MessageChunk]:
    cps = list(text)
    n = len(cps)
    if n == 0:
        return []
    if n <= size:
        return [MessageChunk(0, 0, n, text)]
    step = max(1, size - overlap)
    out: list[MessageChunk] = []
    i = 0
    idx = 0
    while i < n:
        j = min(n, i + size)
        window = "".join(cps[i:j])
        cut = j
        if j < n:
            for sep in ("\n\n", "\n", "。", "！", "？", ". ", "! ", "? "):
                pos = window.rfind(sep)
                if pos >= size // 3:
                    cut = i + pos + len(list(sep))
                    break
        piece = "".join(cps[i:cut])
        out.append(MessageChunk(idx, i, cut, piece))
        idx += 1
        if cut >= n:
            break
        i = max(cut - overlap, i + 1)
    return out


def coverage_ok(text: str, chunks: list[MessageChunk]) -> bool:
    n = len(list(text))
    if n == 0:
        return chunks == []
    covered = [False] * n
    for c in chunks:
        for i in range(c.start_char, c.end_char):
            if 0 <= i < n:
                covered[i] = True
    return all(covered)
