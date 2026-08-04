from __future__ import annotations

import json
import re
from typing import Protocol

from app.engine.memory.models import ExtractionResult, MemoryCandidate
from app.engine.memory.normalize import infer_category
from app.engine.memory.policy import extraction_after_evidence_gate, is_template_like
from app.engine.secrets import scan_secrets
from app.models.llm import LLMClient

# 生产默认：LLM 可改写 statement，evidence 锚定原文。
# 测试/无 LLM 环境使用 RuleBasedMemoryExtractor（statement 为原文逐字摘录）。

_SYSTEM_PROMPT = """你是用户长期记忆抽取器。只分析「用户本条消息」，提取可长期复用的个人画像事实（身份、稳定偏好、长期目标、常用工具/环境、明确约束）。

必须忽略：
- 提问、命令、一次性任务、代码块、链接摘要
- 提示词/模板/填空示例（含 ______、____、（职业）、「填入」等占位）
- 书籍阅读模板、第三方或虚构人物描述
- 不确定的推测（除非用户明确用「可能」「好像」且仍在描述自己）

规则：
1. statement：写入记忆文件的表述。可理解用户原意后整理改写，要求完整、简洁、可读（优先第一人称「我…」），适合长期画像；不要占位符、不要只留半句标签（如仅「我是一名工程师」而省略职责与专长）。同一消息内若有多条独立事实，拆成多条 candidate，每条 statement 自洽完整。
2. evidence：必须是用户本条消息中的连续子串，逐字一致，不得改写；用于证明该事实出自用户原话，应覆盖 statement 所依据的原文（可一句或多句，不必与 statement 字面相同）。
3. category 取其一：identity / preference / goal / workflow / constraint
4. origin：用户明确自述用 direct；从上下文合理推断用 inferred
5. confidence：direct 通常 0.85–1.0；inferred 通常 0.5–0.75
6. 无合适事实时返回空数组

只输出 JSON，不要 markdown 围栏：
{"candidates":[{"statement":"...","evidence":"...","category":"preference","origin":"direct","confidence":0.9}]}"""


class MemoryExtractor(Protocol):
    def extract(
        self, text: str, *, context_messages: list[dict] | None = None
    ) -> ExtractionResult: ...


def locate_statement_span(text: str, statement: str) -> tuple[int, int] | None:
    """在原文中定位 statement 的字符区间（用于证据校验）。"""
    raw = (statement or "").strip()
    if not raw or not text:
        return None
    idx = text.find(raw)
    if idx >= 0:
        return idx, idx + len(raw)
    compact_text = re.sub(r"\s+", " ", text)
    compact_stmt = re.sub(r"\s+", " ", raw)
    idx = compact_text.find(compact_stmt)
    if idx < 0:
        return None
    # 映射回原文近似位置：在原文中滑动匹配（去空白）
    ti = 0
    si = 0
    start = None
    while ti < len(text) and si < len(compact_stmt):
        while ti < len(text) and text[ti].isspace():
            ti += 1
        if ti >= len(text):
            break
        if text[ti] != compact_stmt[si]:
            start = None
            si = 0
            ti += 1
            continue
        if start is None:
            start = ti
        ti += 1
        si += 1
    if si == len(compact_stmt) and start is not None:
        return start, ti
    return None


def _parse_llm_json(raw: str) -> list[dict]:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    items = data.get("candidates")
    return items if isinstance(items, list) else []


class LLMMemoryExtractor:
    """用大模型从用户消息抽取记忆候选（生产默认）。"""

    def __init__(self, llm: LLMClient, *, max_candidates: int = 3):
        self.llm = llm
        self.max_candidates = max_candidates

    def extract(
        self, text: str, *, context_messages: list[dict] | None = None
    ) -> ExtractionResult:
        stripped = (text or "").strip()
        if not stripped or scan_secrets(stripped):
            return ExtractionResult(candidates=[])

        context_block = ""
        if context_messages:
            lines = []
            for m in context_messages[-4:]:
                role = m.get("role", "user")
                if role not in ("user", "assistant"):
                    continue
                body = (m.get("content") or m.get("text") or "").strip()
                if body:
                    lines.append(f"{role}: {body[:400]}")
            if lines:
                context_block = "近期对话（仅作消歧，仍以本条用户消息为准）：\n" + "\n".join(
                    lines
                )

        user_content = f"用户本条消息：\n{stripped}"
        if context_block:
            user_content = context_block + "\n\n" + user_content

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        raw = self.llm.chat(messages, big=False, temperature=0.1).strip()
        candidates: list[MemoryCandidate] = []
        for item in _parse_llm_json(raw)[: self.max_candidates]:
            if not isinstance(item, dict):
                continue
            statement = str(item.get("statement", "")).strip()
            if len(statement) < 3 or is_template_like(statement):
                continue
            if scan_secrets(statement):
                continue
            evidence = str(item.get("evidence") or statement).strip()
            if len(evidence) < 3 or scan_secrets(evidence) or is_template_like(evidence):
                continue
            span = locate_statement_span(stripped, evidence)
            if span is None:
                continue
            start, end = span
            category = str(item.get("category") or infer_category(statement)).strip()
            if category not in (
                "identity",
                "preference",
                "goal",
                "workflow",
                "constraint",
            ):
                category = infer_category(statement)
            origin = str(item.get("origin") or "direct").strip()
            if origin not in ("direct", "inferred"):
                origin = "direct"
            try:
                confidence = float(item.get("confidence", 0.85 if origin == "direct" else 0.65))
            except (TypeError, ValueError):
                confidence = 0.85 if origin == "direct" else 0.65
            confidence = max(0.0, min(1.0, confidence))
            rewritten = statement != evidence
            candidates.append(
                MemoryCandidate(
                    statement=statement,
                    category=category,
                    origin=origin,
                    confidence=confidence,
                    start_char=start,
                    end_char=end,
                    rewritten=rewritten,
                )
            )
        return extraction_after_evidence_gate(stripped, candidates)
