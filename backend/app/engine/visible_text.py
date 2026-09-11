"""Strip model-leaked tool/function protocol markup from assistant-visible text.

Root cause: some models (GLM / Qwen / MiniMax 等) emit XML-style tool-call
wrappers into ``content`` / ``text_delta`` instead of only structured
``tool_calls``. Those tags are protocol, not user-facing prose.

This module strips that *class* of wrappers — not a single leaked string.
"""

from __future__ import annotations

import re

# optional vendor prefix + optional "old_" + function|tool + call/result/…
_TAG_NAME = (
    r"(?:[\w.-]+:)?"
    r"(?:old[_-])?"
    r"(?:function|tool)"
    r"[_-]"
    r"(?:calls?|results?|responses?|outputs?)"
)

_OPEN = re.compile(rf"<(?P<name>{_TAG_NAME})\s*/?>", re.IGNORECASE)
_CLOSE = re.compile(rf"</(?P<name>{_TAG_NAME})\s*>", re.IGNORECASE)
_BLOCK = re.compile(
    rf"<({_TAG_NAME})\s*>"
    rf".*?"
    rf"</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_SELF_CLOSING = re.compile(rf"<({_TAG_NAME})\s*/>", re.IGNORECASE)
_ANY_TAG = re.compile(rf"</?(?:{_TAG_NAME})\s*/?>", re.IGNORECASE)
_QWEN_BLOCK = re.compile(
    r"<(function|parameter)=[^\s>/]+>"
    r".*?"
    r"</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_QWEN_ATTR = re.compile(
    r"</?(?:function|parameter)(?:=[^\s>/]+)?\s*>",
    re.IGNORECASE,
)
_FENCE = re.compile(r"(```.*?```|~~~.*?~~~)", re.DOTALL)
_BLANK_LINES = re.compile(r"\n{3,}")

_INCOMPLETE_HOLD_MAX = 64


def strip_protocol_markup(text: str) -> str:
    """Remove tool/function protocol XML from complete assistant text."""
    if not text:
        return text
    if "<" in text:
        parts = _FENCE.split(text)
        text = "".join(
            part if i % 2 == 1 else _strip_unfenced(part)
            for i, part in enumerate(parts)
        )
    return _tidy(text)


def _strip_unfenced(text: str) -> str:
    text = _BLOCK.sub("", text)
    text = _QWEN_BLOCK.sub("", text)
    text = _SELF_CLOSING.sub("", text)
    text = _ANY_TAG.sub("", text)
    text = _QWEN_ATTR.sub("", text)
    return text


def _tidy(text: str) -> str:
    return _BLANK_LINES.sub("\n\n", text).strip("\n")


def _should_escape_unclosed(interior: str) -> bool:
    """Unclosed wrapper must not swallow a real reply."""
    s = interior.lstrip("\n")
    if not s or s[0] in "{<[":
        return False
    if any("\u4e00" <= ch <= "\u9fff" for ch in s[:40]):
        return True
    return len(s) >= 24


def _maybe_incomplete_tag(fragment: str) -> bool:
    if not fragment.startswith("<") or ">" in fragment:
        return False
    if len(fragment) > _INCOMPLETE_HOLD_MAX:
        return False
    body = fragment[1:]
    if body.startswith("/"):
        body = body[1:]
    return bool(re.fullmatch(r"[\w.:-]*=?", body, re.IGNORECASE)) or body == ""


class VisibleTextStream:
    """Streaming counterpart: hold incomplete ``<`` and swallow matched blocks."""

    def __init__(self) -> None:
        self._buf = ""
        self._in_block: str | None = None

    def push(self, delta: str) -> list[str]:
        if not delta:
            return []
        self._buf += delta
        return self._drain(flush=False)

    def flush(self) -> list[str]:
        pieces = self._drain(flush=True)
        leftover = strip_protocol_markup(self._buf) if self._buf else ""
        self._buf = ""
        self._in_block = None
        if leftover:
            pieces.append(leftover)
        return pieces

    def _drain(self, *, flush: bool) -> list[str]:
        out: list[str] = []
        while self._buf:
            if self._in_block:
                close = re.search(
                    rf"</{re.escape(self._in_block)}\s*>",
                    self._buf,
                    re.IGNORECASE,
                )
                if close:
                    self._buf = self._buf[close.end() :].lstrip("\n")
                    self._in_block = None
                    continue
                if not flush and not _should_escape_unclosed(self._buf):
                    return out
                kept = strip_protocol_markup(self._buf)
                self._buf = ""
                self._in_block = None
                if kept:
                    out.append(kept)
                return out

            first: re.Match[str] | None = None
            kind = ""
            opened = _OPEN.search(self._buf)
            closed = _CLOSE.search(self._buf)
            if opened and (not closed or opened.start() <= closed.start()):
                first, kind = opened, "open"
            elif closed:
                first, kind = closed, "close"

            if first is None:
                lt = self._buf.rfind("<")
                if lt != -1 and not flush and _maybe_incomplete_tag(self._buf[lt:]):
                    safe = self._buf[:lt]
                    self._buf = self._buf[lt:]
                    if safe:
                        out.append(safe)
                    return out
                if self._buf:
                    out.append(self._buf)
                    self._buf = ""
                return out

            if first.start() > 0:
                out.append(self._buf[: first.start()])
            token = first.group(0)
            if kind == "open" and not token.rstrip().endswith("/>"):
                self._in_block = first.group("name")
            self._buf = self._buf[first.end() :].lstrip("\n")
        return out


__all__ = ["strip_protocol_markup", "VisibleTextStream"]
