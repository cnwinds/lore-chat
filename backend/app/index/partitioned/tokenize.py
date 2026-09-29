from __future__ import annotations

import unicodedata

TOKENIZER_VERSION = 1

# 与 ADR 一致：假名、CJK 扩展/统一、兼容区、谚文
_CJK_RANGES = (
    (0x3040, 0x30FF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0xAC00, 0xD7AF),
)


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    for lo, hi in _CJK_RANGES:
        if lo <= o <= hi:
            return True
    return False


def _tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if _is_cjk(ch):
            j = i + 1
            while j < n and _is_cjk(text[j]):
                j += 1
            seg = text[i:j]
            if len(seg) == 1:
                tokens.append(seg)
            else:
                for k in range(len(seg) - 1):
                    tokens.append(seg[k : k + 2])
            i = j
        elif ch.isalnum():
            j = i + 1
            while j < n and text[j].isalnum() and not _is_cjk(text[j]):
                j += 1
            tokens.append(text[i:j])
            i = j
        else:
            i += 1
    return tokens


def index_terms(text: str) -> list[str]:
    return _tokenize(text)


def query_terms(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in _tokenize(text):
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
