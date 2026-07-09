from __future__ import annotations

import json
from dataclasses import dataclass

from app.storage.repo import KnowledgeRepo
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
        summary = self._understand(content)
        related = self.retriever.search(summary or content, k=5)
        decision = self._decide(content, summary, related)

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
                    "你是知识库组织员。根据新内容和已有相关文档，决定如何归置。"
                    "只输出 JSON，字段：action(new|merge|append), rel_path(目标md相对路径,以.md结尾), "
                    "title, category(目录,如 技术/docker,可空), tags(数组), ambiguous(bool,重叠但拿不准时true), reason。"
                    "若与某已有文档明显是同一主题应 merge/append；全新主题用 new；拿不准是否重叠时 ambiguous=true。"
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
