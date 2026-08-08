from __future__ import annotations

import hashlib
import re
import unicodedata
from difflib import SequenceMatcher

from app.engine.memory.predicates import SEED_PREDICATES, get_seed

_WS_RE = re.compile(r"\s+")
_SLOT_RE = re.compile(
    r"^(?P<cat>identity|preference|goal|project|workflow|constraint)\.(?P<pred>[a-z0-9_\u4e00-\u9fff]+)$"
)
_PRED_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_CATEGORIES = frozenset(
    {"identity", "preference", "goal", "project", "workflow", "constraint"}
)
_LATIN_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = _WS_RE.sub(" ", text.strip().lower())
    return text


def value_hash(statement: str) -> str:
    return hashlib.sha256(normalize_text(statement).encode("utf-8")).hexdigest()


def canonicalize_slot_key(slot_key: str) -> str | None:
    raw = (slot_key or "").strip().lower().replace("-", "_")
    m = _SLOT_RE.match(raw)
    if m:
        return f"{m.group('cat')}.{m.group('pred')}"
    if "." in raw:
        cat, pred = raw.split(".", 1)
        if cat in _CATEGORIES and pred:
            return f"{cat}.{pred}"
    return None


def is_abstract_slot_key(slot_key: str) -> bool:
    """抽象槽：category + 英文蛇形谓词；不含 statement stem / 中文 / 旧 open_ 全文指纹。"""
    key = canonicalize_slot_key(slot_key)
    if not key:
        return False
    _cat, pred = key.split(".", 1)
    if any("\u4e00" <= ch <= "\u9fff" for ch in pred):
        return False
    # 旧实现：open_{statement_stem}_{digest} —— 禁止当作稳定抽象槽保留
    if pred.startswith("open_"):
        return False
    return bool(_PRED_RE.match(pred))


def match_seed_slot(statement: str, *, category: str | None = None) -> str | None:
    """按别名启发式对齐种子槽；返回最佳 slot_key 或 None。"""
    text = normalize_text(statement)
    if not text:
        return None
    best_key: str | None = None
    best_score = 0
    for pred in SEED_PREDICATES:
        if category and pred.category != category.strip().lower():
            continue
        score = 0
        for alias in pred.aliases:
            a = normalize_text(alias)
            if a and a in text:
                score += max(len(a), 1)
        if score > best_score:
            best_score = score
            best_key = pred.slot_key
    # 至少命中一段有意义别名（避免单字误触）；约束类「不要」较短，阈值放宽到 2
    if best_score < 2:
        return None
    return best_key


def significant_tokens(statement: str) -> set[str]:
    """近义对齐用 token：拉丁词 + 汉字 bigram。"""
    text = normalize_text(statement)
    tokens: set[str] = set(_LATIN_TOKEN_RE.findall(text))
    for run in _CJK_RUN_RE.findall(text):
        if len(run) == 1:
            tokens.add(run)
        else:
            for i in range(len(run) - 1):
                tokens.add(run[i : i + 2])
    return tokens


def align_existing_slot(
    statement: str,
    *,
    category: str | None = None,
    existing: list[dict] | None = None,
    min_score: float = 0.5,
    min_overlap: int = 5,
) -> str | None:
    """若与已有画像近义，复用其抽象 slot（避免开放槽按措辞分裂）。"""
    if not existing:
        return None
    text = normalize_text(statement)
    tokens = significant_tokens(statement)
    if len(tokens) < 2 or len(text) < 8:
        return None
    cat = (category or "").strip().lower()
    best_key: str | None = None
    best = 0.0
    for fact in existing:
        if cat:
            fcat = (fact.get("category") or "").strip().lower()
            if fcat and fcat != cat:
                continue
        other_stmt = str(fact.get("statement") or "")
        other = significant_tokens(other_stmt)
        if len(other) < 2:
            continue
        overlap = tokens & other
        if len(overlap) < min_overlap:
            continue
        coverage = len(overlap) / max(min(len(tokens), len(other)), 1)
        seq = SequenceMatcher(None, text, normalize_text(other_stmt)).ratio()
        sk = str(fact.get("slot_key") or "")
        cand = canonicalize_slot_key(sk) or sk
        if not cand or not is_abstract_slot_key(cand):
            continue  # 不复用旧 open_/中文 stem 槽
        score = 0.5 * seq + 0.5 * coverage
        if score > best:
            best = score
            best_key = cand
    if best >= min_score and best_key:
        return best_key
    return None


def _fallback_topic_predicate(statement: str) -> str:
    """末路开放槽：仅内容指纹，禁止 statement stem（规格 §5.1）。"""
    return f"topic_{value_hash(statement)[:12]}"


def normalize_slot_key(
    category: str,
    statement: str,
    *,
    existing: list[dict] | None = None,
) -> str:
    """解析或推断抽象 slot_key。

    - 已是 `category.predicate` → 规范化返回
    - 仅为英文蛇形 predicate → 拼成完整 slot
    - 命中种子别名 → 种子 slot
    - 与已有画像近义 → 复用其 slot
    - 否则 → `category.topic_{hash}`（无 stem）
    """
    cat = (category or "preference").strip().lower() or "preference"
    raw = (statement or "").strip()
    if not raw:
        return f"{cat}.unknown"

    explicit = canonicalize_slot_key(raw)
    # 仅保留抽象槽；旧 open_/中文 stem 视为无效，继续按正文对齐
    if explicit and is_abstract_slot_key(explicit):
        return explicit

    pred_only = raw.lower().replace("-", "_")
    if _PRED_RE.match(pred_only) and not pred_only.startswith("open_"):
        return f"{cat}.{pred_only}"

    seeded = match_seed_slot(raw, category=cat)
    if seeded:
        return seeded
    seeded = match_seed_slot(raw)
    if seeded:
        return seeded

    aligned = align_existing_slot(raw, category=cat, existing=existing)
    if aligned:
        return aligned

    return f"{cat}.{_fallback_topic_predicate(raw)}"


def resolve_slot_key(
    category: str,
    statement: str,
    *,
    slot_hint: str | None = None,
    existing: list[dict] | None = None,
) -> str:
    """抽取/写入共用：显式抽象 hint → 否则 normalize（种子/近义/topic_）。"""
    hint = canonicalize_slot_key(slot_hint or "")
    if hint and is_abstract_slot_key(hint):
        # 正文能命中种子时优先种子，避免 LLM 为近义各开新 topic_*
        seeded = match_seed_slot(statement)
        if seeded:
            return seeded
        aligned = align_existing_slot(
            statement, category=category, existing=existing
        )
        if aligned:
            return aligned
        return hint
    return normalize_slot_key(category, statement, existing=existing)


def infer_category(statement: str) -> str:
    text = statement.strip()
    seeded = match_seed_slot(text)
    if seeded:
        seed = get_seed(seeded)
        if seed:
            return seed.category
    if any(k in text for k in ("约束", "不要", "禁止", "不能")):
        return "constraint"
    if any(k in text for k in ("目标", "正在做", "项目")):
        return "goal"
    if any(k in text for k in ("身份", "我是", "住在", "工作于")):
        return "identity"
    if any(k in text for k in ("工具", "环境", "流程", "工作方式", "scripts")):
        return "workflow"
    return "preference"
