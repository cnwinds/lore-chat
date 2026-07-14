from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*\S{8,}"),
]


@dataclass(frozen=True)
class SecretSpan:
    start: int  # unicode code point index
    end: int    # exclusive


def _codepoints(text: str) -> list[str]:
    return list(text)


def scan_secrets(text: str) -> list[SecretSpan]:
    cps = _codepoints(text)
    joined = "".join(cps)
    spans: list[SecretSpan] = []
    for pat in _PATTERNS:
        for m in pat.finditer(joined):
            spans.append(SecretSpan(m.start(), m.end()))
    # merge overlaps
    if not spans:
        return []
    spans.sort(key=lambda s: (s.start, s.end))
    merged = [spans[0]]
    for s in spans[1:]:
        last = merged[-1]
        if s.start <= last.end:
            merged[-1] = SecretSpan(last.start, max(last.end, s.end))
        else:
            merged.append(s)
    return merged


def mask_secrets(text: str, mask_char: str = "•") -> tuple[str, list[SecretSpan]]:
    cps = _codepoints(text)
    spans = scan_secrets(text)
    for s in spans:
        for i in range(s.start, min(s.end, len(cps))):
            cps[i] = mask_char
    return "".join(cps), spans
