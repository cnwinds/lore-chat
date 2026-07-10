from __future__ import annotations

import json
from dataclasses import dataclass

from app.storage.repo import KnowledgeRepo
from app.engine.intent import is_question_only
from app.engine.retriever import Retriever
from app.engine.pending import PendingStore
from app.index.indexer import Indexer
from app.models.llm import LLMClient


@dataclass
class PlacementDecision:
    action: str
    rel_path: str
    title: str
    category: str
    tags: list[str]
    ambiguous: bool
    reason: str


@dataclass
class IngestResult:
    status: str
    rel_path: str | None
    question_id: str | None
    message: str


class Organizer:
    def __init__(
        self,
        repo: KnowledgeRepo,
        retriever: Retriever,
        indexer: Indexer,
        pending: PendingStore,
        llm: LLMClient,
    ):
        self.repo = repo
        self.retriever = retriever
        self.indexer = indexer
        self.pending = pending
        self.llm = llm

    def ingest_text(self, content: str) -> IngestResult:
        if is_question_only(content):
            return IngestResult(
                status="rejected",
                rel_path=None,
                question_id=None,
                message="这是提问而非资料，未写入知识库。",
            )

        summary = self._understand(content)
        related = self.retriever.search(summary or content, k=5)
        decision = self._normalize_decision(self._decide(content, summary, related), related)

        if decision.ambiguous:
            qid = self.pending.create(
                question=f"这条内容可能与《{decision.rel_path}》重叠：{decision.reason}。如何处理？",
                options=[
                    {"id": "merge", "label": f"合并进 {decision.rel_path}"},
                    {"id": "new", "label": "新建独立文档"},
                ],
                payload={"content": content, "decision": decision.__dict__},
            )
            return IngestResult(
                status="question",
                rel_path=None,
                question_id=qid,
                message="需要你确认如何归置这条内容。",
            )

        self._apply(decision, content)
        return IngestResult(
            status="saved",
            rel_path=decision.rel_path,
            question_id=None,
            message=f"已保存到 {decision.rel_path}",
        )

    def resolve_pending(self, qid: str, choice: str) -> IngestResult:
        q = self.pending.get(qid)
        content = q["payload"]["content"]
        d = q["payload"]["decision"]
        decision = PlacementDecision(
            **{
                **d,
                "action": "merge" if choice == "merge" else "new",
                "ambiguous": False,
            }
        )
        self._apply(decision, content)
        self.pending.resolve(qid, choice)
        return IngestResult(
            status="saved",
            rel_path=decision.rel_path,
            question_id=None,
            message=f"已按你的选择保存到 {decision.rel_path}",
        )

    def _understand(self, content: str) -> str:
        messages = [
            {"role": "system", "content": "用一句话概括这条内容的主题，便于检索。"},
            {"role": "user", "content": content},
        ]
        return self.llm.chat(messages)

    def _decide(self, content: str, summary: str, related) -> PlacementDecision:
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
                    "1. 与已有文档同一主题、同一问题的补充 → merge/append 到最相关的一篇，ambiguous=false\n"
                    "2. 不要为同一主题创建重复文档；已有相关文档时优先合并\n"
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

    def _normalize_decision(self, decision: PlacementDecision, related) -> PlacementDecision:
        """有相关文档时自动合并，不再向用户确认。"""
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

    def _apply(self, decision: PlacementDecision, content: str) -> None:
        rel_path = decision.rel_path
        exists = False
        try:
            self.repo.read_doc(rel_path)
            exists = True
        except FileNotFoundError:
            exists = False

        if decision.action in ("merge", "append") and exists:
            self.repo.append_doc(
                rel_path,
                f"\n{content}\n",
                commit_msg=f"merge: 追加内容到 {rel_path}",
            )
            verb = "追加到"
        else:
            self.repo.write_doc(
                rel_path,
                meta={"title": decision.title, "tags": decision.tags, "source": "chat"},
                body=f"{content}\n",
                commit_msg=f"add: 新建 {rel_path}",
            )
            verb = "创建"

        doc = self.repo.read_doc(rel_path)
        self.indexer.reindex_doc(rel_path, doc.body)
        self.repo.log_change(
            f"{verb} {rel_path}：{decision.reason or decision.title}",
            commit_msg=f"chore: changelog for {rel_path}",
        )
