from __future__ import annotations

import hashlib
import re
import unicodedata

_WS_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = _WS_RE.sub(" ", text.strip().lower())
    return text


def value_hash(statement: str) -> str:
    return hashlib.sha256(normalize_text(statement).encode("utf-8")).hexdigest()


def normalize_slot_key(category: str, statement: str) -> str:
    cat = (category or "preference").strip().lower()
    stem = normalize_text(statement)[:80] or "unknown"
    stem = re.sub(r"[^a-z0-9\u4e00-\u9fff._:-]+", "_", stem)
    return f"{cat}.{stem}"


def infer_category(statement: str) -> str:
    text = statement.strip()
    if any(k in text for k in ("约束", "不要", "禁止", "不能")):
        return "constraint"
    if any(k in text for k in ("目标", "正在做", "项目")):
        return "goal"
    if any(k in text for k in ("身份", "我是", "住在", "工作于")):
        return "identity"
    if any(k in text for k in ("工具", "环境", "流程", "工作方式")):
        return "workflow"
    return "preference"
