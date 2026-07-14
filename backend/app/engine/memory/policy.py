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


def infer_sensitivity(statement: str) -> str:
    text = (statement or "").strip()
    if not text:
        return "normal"
    if any(kw in text for kw in _SENSITIVE_KEYWORDS):
        return "sensitive"
    if re.search(r"\d+号", text) and any(k in text for k in ("路", "街", "区", "市")):
        return "sensitive"
    return "normal"
