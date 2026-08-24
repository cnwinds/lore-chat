"""检索 query 编译：strict → relaxed FTS 与向量文本的单一来源。"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 协议/格式类拉丁词：不得单独进入 relaxed OR（可在短语内保留）
_LOW_SIGNAL_LATIN = frozenset(
    {"url", "http", "https", "api", "www", "com", "org", "net"}
)

_LATIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class CompiledSearchQuery:
    vector_text: str
    strict_fts: str | None
    relaxed_fts: str | None
    signal_terms: tuple[str, ...]
    like_terms: tuple[str, ...]
    match_terms: tuple[str, ...]


def compile_search_query(text: str, *, max_len: int = 300) -> CompiledSearchQuery:
    text = " ".join((text or "").split())
    if not text:
        return CompiledSearchQuery("", None, None, (), (), ())
    if len(text) > max_len:
        text = text[:max_len]

    terms = _extract_terms(text)
    signal = _signal_terms(terms)
    match_terms = tuple(terms) if terms else signal
    like_terms = tuple(
        t for t in signal if _term_codepoints(t) >= 3 or " " in t
    )
    if not like_terms and signal:
        like_terms = signal

    strict = _build_strict_fts(signal)
    relaxed = _build_relaxed_fts(signal)

    vector_text = " ".join(signal) if signal else text
    return CompiledSearchQuery(
        vector_text=vector_text,
        strict_fts=strict,
        relaxed_fts=relaxed,
        signal_terms=signal,
        like_terms=like_terms,
        match_terms=match_terms,
    )


def prepare_fts_query(text: str, *, max_len: int = 300) -> str:
    """兼容入口：返回 relaxed FTS 表达式（旧测试与外部调用）。"""
    compiled = compile_search_query(text, max_len=max_len)
    if compiled.relaxed_fts:
        return compiled.relaxed_fts
    if compiled.strict_fts:
        return compiled.strict_fts
    return ""


def _term_codepoints(term: str) -> int:
    return len(list(term))


def _is_latin_token(part: str) -> bool:
    return bool(_LATIN_RE.match(part))


def _is_low_signal(token: str) -> bool:
    return token.lower() in _LOW_SIGNAL_LATIN


def _extract_terms(text: str) -> list[str]:
    """空白分词；连续拉丁词合并为短语。"""
    parts = text.split()
    terms: list[str] = []
    latin_buf: list[str] = []

    def flush_latin() -> None:
        nonlocal latin_buf
        if not latin_buf:
            return
        if len(latin_buf) == 1 and _is_low_signal(latin_buf[0]):
            latin_buf = []
            return
        terms.append(" ".join(latin_buf))
        latin_buf = []

    for part in parts:
        if _is_latin_token(part):
            if _is_low_signal(part):
                flush_latin()
                continue
            latin_buf.append(part)
        else:
            flush_latin()
            terms.append(part)
    flush_latin()
    return terms


def _signal_terms(terms: list[str]) -> tuple[str, ...]:
    """进入 relaxed / 门控的有效词：中文 ≥3 字或拉丁短语。"""
    usable = [
        t
        for t in terms
        if _term_codepoints(t) >= 3 or " " in t
    ]
    if not usable:
        usable = list(terms)
    return tuple(usable)


def _phrase(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def _build_strict_fts(signal: tuple[str, ...]) -> str | None:
    if not signal:
        return None
    if len(signal) == 1:
        return _phrase(signal[0])
    if len(signal) <= 4:
        return " AND ".join(_phrase(t) for t in signal)
    return None


def _build_relaxed_fts(signal: tuple[str, ...]) -> str | None:
    if not signal:
        return None
    if len(signal) == 1:
        return _phrase(signal[0])
    return " OR ".join(_phrase(t) for t in signal)
