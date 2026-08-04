from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.engine.retriever import Retriever
from app.models.llm import LLMClient
from app.storage.kb_paths import title_from_rel_path
from app.storage.repo import KnowledgeRepo


@dataclass
class PlacementDecision:
    action: str
    rel_path: str
    title: str
    category: str
    tags: list[str]
    ambiguous: bool
    reason: str


class PlacementPlanner:
    """LLM 归位决策；落盘由 KnowledgeWriter / Organizer._apply 负责。"""

    def __init__(self, repo: KnowledgeRepo, retriever: Retriever, llm: LLMClient):
        self.repo = repo
        self.retriever = retriever
        self.llm = llm

    def understand(self, content: str) -> str:
        messages = [
            {"role": "system", "content": "用一句话概括这条内容的主题，便于检索。"},
            {"role": "user", "content": content},
        ]
        return self.llm.chat(messages)

    def decide(self, content: str, summary: str, related) -> PlacementDecision:
        related_desc = (
            "\n".join(f"- {h.source}: {h.chunk[:80]}" for h in related)
            or "（无相关文档）"
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是知识库组织员。果断决策，避免让用户确认。\n"
                    "规则：\n"
                    "1. 与已有文档同一主题、同一问题的补充 → merge 到最相关的一篇"
                    "（系统会读取原文并整篇重组为完整文档，非简单追加），ambiguous=false\n"
                    "2. 不要为同一主题创建重复文档；已有相关文档时优先 merge\n"
                    "3. 全新主题 → action=new\n"
                    "4. ambiguous=true 仅在完全无法判断归到哪篇时使用（应极少出现）\n"
                    "只输出 JSON：action(new|merge|append), rel_path(以.md结尾), "
                    "title, category(如 技术/powershell), tags(数组), ambiguous(bool), reason"
                ),
            },
            {
                "role": "user",
                "content": f"新内容：{content}\n摘要：{summary}\n相关文档：\n{related_desc}",
            },
        ]
        raw = self.llm.chat(messages)
        data = self._parse_json(raw)
        return PlacementDecision(
            action=data.get("action", "new"),
            rel_path=data.get("rel_path") or "未分类/note.md",
            title=data.get("title", "未命名"),
            category=data.get("category", ""),
            tags=data.get("tags", []),
            ambiguous=bool(data.get("ambiguous", False)),
            reason=data.get("reason", ""),
        )

    def decision_for_forced_path(self, rel_path: str) -> PlacementDecision:
        norm = rel_path.replace("\\", "/").lstrip("/")
        title = title_from_rel_path(norm)
        category = norm.rsplit("/", 1)[0] if "/" in norm else ""
        try:
            self.repo.read_doc(norm)
            exists = True
        except FileNotFoundError:
            exists = False
        if exists:
            return PlacementDecision(
                action="merge",
                rel_path=norm,
                title=title,
                category=category,
                tags=[],
                ambiguous=False,
                reason=f"合并到指定路径 {norm}",
            )
        return PlacementDecision(
            action="new",
            rel_path=norm,
            title=title,
            category=category,
            tags=[],
            ambiguous=False,
            reason=f"新建于指定路径 {norm}",
        )

    def apply_hint_path(
        self, decision: PlacementDecision, hint_path: str | None
    ) -> PlacementDecision:
        if not hint_path:
            return decision
        try:
            doc = self.repo.read_doc(hint_path)
        except FileNotFoundError:
            return decision
        return PlacementDecision(
            action="merge",
            rel_path=hint_path,
            title=decision.title or doc.meta.get("title", ""),
            category=decision.category,
            tags=decision.tags,
            ambiguous=False,
            reason=decision.reason or f"合并到用户正在查看的 {hint_path}",
        )

    def normalize_decision(self, decision: PlacementDecision, related) -> PlacementDecision:
        if not decision.ambiguous:
            if decision.action in ("merge", "append") and related:
                related_paths = {h.source for h in related}
                if decision.rel_path not in related_paths:
                    decision = PlacementDecision(
                        action="merge",
                        rel_path=related[0].source,
                        title=decision.title,
                        category=decision.category,
                        tags=decision.tags,
                        ambiguous=False,
                        reason=decision.reason or f"合并到 {related[0].source}",
                    )
            return decision

        if related:
            target = decision.rel_path
            related_paths = {h.source for h in related}
            if target not in related_paths:
                target = related[0].source
            return PlacementDecision(
                action="merge",
                rel_path=target,
                title=decision.title,
                category=decision.category,
                tags=decision.tags,
                ambiguous=False,
                reason=decision.reason or f"自动合并到 {target}",
            )
        return decision

    @staticmethod
    def _parse_json(raw: str) -> dict:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start : end + 1]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
