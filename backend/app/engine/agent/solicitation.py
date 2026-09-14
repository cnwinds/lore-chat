"""Detect plaintext solicitations that should have been ask_user.

Root cause: the product UI only renders a question card from a structured
``ask_user`` tool result. Some models (and our own history projection, before
it was tightened) write a 「【征询】…选项：…」 block into assistant prose
instead of calling the tool. That class of leak is protocol, not user-facing
copy — promote it deterministically rather than hoping the next sample
remembers to call the tool.

Tradeoff: only high-confidence trailing blocks are promoted (explicit marker +
≥2 options). Ordinary numbered advice without the marker stays prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Markers we ourselves taught (legacy history) or still teach (tool report).
_MARKERS = (
    "【征询】",
    "已通过 ask_user 向用户提问：",
    "已通过 ask_user 向用户提问:",
)

_OPTION_HEADER = re.compile(r"(?:选项|可选)\s*[：:]")
_OPTION_LINE = re.compile(
    r"^\s*(?:[-*•]|\d{1,2}\s*[.)、．）]|[A-Ha-h]\s*[.)、．）])\s*(\S.+?)\s*$"
)
_MULTI_HINT = re.compile(r"可多选|(?<![一不])多选")

_MIN_OPTIONS = 2
_MAX_OPTIONS = 12
_MAX_QUESTION_CHARS = 200
_MAX_LABEL_CHARS = 500


@dataclass(frozen=True)
class ParsedSolicitation:
    question: str
    options: list[dict]
    multi_select: bool
    remainder: str


def parse_plaintext_solicitation(text: str) -> ParsedSolicitation | None:
    """Return a trailing plaintext ask, or None if the text is ordinary prose."""
    raw = (text or "").strip("\n")
    if not raw or not any(marker in raw for marker in _MARKERS):
        return None
    idx, marker = _last_marker(raw)
    if idx < 0:
        return None
    remainder = raw[:idx].rstrip()
    rest = raw[idx + len(marker) :].strip()
    if not rest:
        return None
    question, body = _split_question_and_body(rest)
    question = _clean_question(question)
    if not question or len(question) > _MAX_QUESTION_CHARS:
        return None
    labels = _split_option_labels(body)
    if len(labels) < _MIN_OPTIONS or len(labels) > _MAX_OPTIONS:
        return None
    options = [
        {"id": f"opt{i + 1}", "label": label[:_MAX_LABEL_CHARS]}
        for i, label in enumerate(labels)
    ]
    return ParsedSolicitation(
        question=question,
        options=options,
        multi_select=bool(_MULTI_HINT.search(question)),
        remainder=remainder,
    )


def _last_marker(text: str) -> tuple[int, str]:
    found_at = -1
    found = ""
    for marker in _MARKERS:
        idx = text.rfind(marker)
        if idx > found_at:
            found_at = idx
            found = marker
    return found_at, found


def _split_question_and_body(rest: str) -> tuple[str, str]:
    header = _OPTION_HEADER.search(rest)
    if header:
        return rest[: header.start()].strip(), rest[header.end() :].strip()
    lines = rest.splitlines()
    question = ""
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip():
            question = line.strip()
            body_start = i + 1
            break
    return question, "\n".join(lines[body_start:]).strip()


def _clean_question(question: str) -> str:
    q = question.strip().strip("*").strip()
    q = re.sub(r"\s+", " ", q)
    return q


def _split_option_labels(body: str) -> list[str]:
    if not body:
        return []
    lined = _labels_from_lines(body)
    if len(lined) >= _MIN_OPTIONS:
        return lined
    parts = re.split(r"[；;]", body)
    labels = [_clean_label(p) for p in parts]
    return [x for x in labels if x]


def _labels_from_lines(body: str) -> list[str]:
    labels: list[str] = []
    for line in body.splitlines():
        if not line.strip():
            continue
        m = _OPTION_LINE.match(line)
        if not m:
            return []
        label = _clean_label(m.group(1))
        if not label:
            return []
        labels.append(label)
    return labels


def _clean_label(label: str) -> str:
    s = label.strip().strip("*").strip()
    s = re.sub(r"\s+", " ", s)
    return s


__all__ = ["ParsedSolicitation", "parse_plaintext_solicitation"]
