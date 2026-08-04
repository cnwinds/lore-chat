from __future__ import annotations

import hashlib
import re

from app.engine.memory.models import ExtractionResult, MemoryCandidate
from app.engine.memory.normalize import normalize_slot_key, value_hash

_SENSITIVE_KEYWORDS = (
    "健康",
    "病历",
    "医院",
    "诊断",
    "财务",
    "收入",
    "工资",
    "薪资",
    "银行",
    "住址",
    "地址",
    "住在",
    "身份证",
    "社保",
)

_DIRECT_MARKERS = ("我偏好", "我喜欢", "我习惯", "我通常", "我一般", "我是", "我用", "我使用")
_CHANGE_MARKERS = ("现在", "以后", "改为", "不再", "改成")
_PROMOTION_CONFIDENCE = 0.80
_PROMOTION_MIN_CONVERSATIONS = 2

_TEMPLATE_RE = re.compile(
    r"_{3,}|______|\(职业\)|（职业）|填入你的|填入职业|我读这本书的目的"
)
_MIN_EVIDENCE_QUOTE_LEN = 8
_MIN_EVIDENCE_CORE_LEN = 8
_REWRITE_STMT_EVIDENCE_OVERLAP = 0.35
_PUNCT_STRIP_RE = re.compile(r"[\s，。、；：！？,.;:!?\"'「」【】（）()\[\]{}]+")


def is_template_like(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return True
    if _TEMPLATE_RE.search(s):
        return True
    if "____" in s and len(s) < 40:
        return True
    return False


def _core_chars(text: str) -> str:
    return _PUNCT_STRIP_RE.sub("", text or "")


def rewrite_supported_by_evidence(statement: str, evidence_quote: str) -> bool:
    """改写 statement 须与 evidence 摘录有足够字元重叠，防止短摘录配胡编事实。"""
    stmt = _core_chars(statement)
    ev = _core_chars(evidence_quote)
    if len(ev) < _MIN_EVIDENCE_CORE_LEN or len(stmt) < 2:
        return False
    common = sum(1 for c in stmt if c in ev)
    return common / len(stmt) >= _REWRITE_STMT_EVIDENCE_OVERLAP


def infer_sensitivity(statement: str) -> str:
    text = (statement or "").strip()
    if not text:
        return "normal"
    if any(kw in text for kw in _SENSITIVE_KEYWORDS):
        return "sensitive"
    if re.search(r"\d+号", text) and any(k in text for k in ("路", "街", "区", "市")):
        return "sensitive"
    return "normal"


def validate_evidence(text: str, candidate: MemoryCandidate) -> bool:
    if candidate.start_char < 0 or candidate.end_char > len(text):
        return False
    if candidate.start_char >= candidate.end_char:
        return False
    quote = text[candidate.start_char : candidate.end_char].strip()
    stmt = candidate.statement.strip()
    if not quote or is_template_like(quote):
        return False
    if not candidate.rewritten:
        return quote == stmt or stmt in quote
    if len(quote) < _MIN_EVIDENCE_QUOTE_LEN:
        return False
    return rewrite_supported_by_evidence(stmt, quote)


def validated_candidates(
    text: str, candidates: list[MemoryCandidate]
) -> list[MemoryCandidate]:
    """抽取 adapter 出口：仅保留证据与原文一致的候选。"""
    valid, _ = partition_by_evidence(text, candidates)
    return valid


def partition_by_evidence(
    text: str, candidates: list[MemoryCandidate]
) -> tuple[list[MemoryCandidate], int]:
    valid: list[MemoryCandidate] = []
    rejected = 0
    for c in candidates:
        if validate_evidence(text, c):
            valid.append(c)
        else:
            rejected += 1
    return valid, rejected


def extraction_after_evidence_gate(
    text: str, candidates: list[MemoryCandidate]
) -> ExtractionResult:
    valid, rejected = partition_by_evidence(text, candidates)
    return ExtractionResult(
        candidates=valid, rejected_evidence_count=rejected
    )


def is_direct_self_statement(statement: str) -> bool:
    text = (statement or "").strip()
    return any(text.startswith(m) or m in text[:20] for m in _DIRECT_MARKERS)


def allows_automatic_save(sensitivity: str, origin: str) -> bool:
    if sensitivity == "secret":
        return False
    if sensitivity == "sensitive" and origin not in ("manual", "explicit_remember"):
        return False
    return True


def initial_status(candidate: MemoryCandidate, *, sensitivity: str) -> str:
    if not allows_automatic_save(sensitivity, candidate.origin):
        return "rejected"
    if candidate.origin == "direct" and is_direct_self_statement(candidate.statement):
        return "confirmed"
    if candidate.origin in ("manual", "explicit_remember"):
        return "confirmed"
    return "candidate"


def should_promote(fact: dict, *, distinct_conversations: int, evidence_count: int) -> bool:
    if fact.get("status") != "candidate":
        return False
    if fact.get("origin") == "inferred":
        if distinct_conversations < _PROMOTION_MIN_CONVERSATIONS:
            return False
        if evidence_count < 2:
            return False
        if float(fact.get("confidence") or 0) < _PROMOTION_CONFIDENCE:
            return False
        return True
    return False


def has_change_signal(statement: str) -> bool:
    return any(m in statement for m in _CHANGE_MARKERS)


def origin_wins_conflict(new_origin: str, old_origin: str) -> bool:
    rank = {"manual": 4, "explicit_remember": 3, "direct": 2, "inferred": 1}
    new_rank = rank.get(new_origin, 0)
    old_rank = rank.get(old_origin, 0)
    if new_rank != old_rank:
        return new_rank > old_rank
    return False


def quote_hash_for(text: str, start: int, end: int) -> str:
    quote = text[start:end]
    return hashlib.sha256(quote.encode("utf-8")).hexdigest()


def slot_for_candidate(candidate: MemoryCandidate) -> tuple[str, str]:
    cat = candidate.category
    stmt = candidate.statement
    return normalize_slot_key(cat, stmt), value_hash(stmt)
