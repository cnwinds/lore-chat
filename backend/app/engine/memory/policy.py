"""SlotResolver 写策略（敏感度、自动落库、冲突/晋升、初始 status）。

按条证据门禁与 MemoryCandidate 已废除；本模块仅服务会话级写路径。
"""

from __future__ import annotations

import re

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

_CHANGE_MARKERS = ("现在", "以后", "改为", "不再", "改成")
_PROMOTION_CONFIDENCE = 0.80
_PROMOTION_MIN_CONVERSATIONS = 2


def infer_sensitivity(statement: str) -> str:
    text = (statement or "").strip()
    if not text:
        return "normal"
    if any(kw in text for kw in _SENSITIVE_KEYWORDS):
        return "sensitive"
    if re.search(r"\d+号", text) and any(k in text for k in ("路", "街", "区", "市")):
        return "sensitive"
    return "normal"


def allows_automatic_save(sensitivity: str, origin: str) -> bool:
    if sensitivity == "secret":
        return False
    if sensitivity == "sensitive" and origin not in ("manual", "explicit_remember"):
        return False
    return True


def initial_status(origin: str, statement: str = "") -> str:
    """由 origin 决定初始 status（statement 保留签名供调用方统一）。"""
    del statement
    if origin in ("manual", "explicit_remember", "direct"):
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
