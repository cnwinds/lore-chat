from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.storage.repo import KnowledgeRepo
from app.engine.intent import is_question_only
from app.engine.retriever import Retriever
from app.engine.pending import PendingStore
from app.index.indexer import Indexer
from app.models.llm import LLMClient


_DEFAULT_SUMMARY_RULES = (
    "1. 总结对象是整段会话，先通读全部对话与依据再动笔。\n"
    "2. 全局重构、禁止流水线拼接：按主题而非发言/来源顺序组织；跨轮去重合并；"
    "禁止用 --- 堆叠多个一级标题，全篇只有一套自洽的标题层级。\n"
    "3. 剥离对话痕迹（如「帮我记录」「用户说」），只留结论与事实。\n"
    "4. 保留可核验性：事实、数据、版本、链接等须有出处，不臆造、不补全。"
)


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
    continue_prompt: str | None = None


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

    def ingest_text(self, content: str, *, hint_path: str | None = None) -> IngestResult:
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
        decision = self._apply_hint_path(decision, hint_path)

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

    def summarize_conversation(
        self,
        transcript: str,
        *,
        hint_path: str | None = None,
        system_rules: str = "",
        conversation_id: str | None = None,
    ) -> IngestResult:
        """把整段会话通读后全局重构成一篇文档并归档（非逐轮拼接）。"""
        if not transcript.strip():
            return IngestResult(
                status="rejected",
                rel_path=None,
                question_id=None,
                message="会话为空，无可总结内容。",
            )
        body = self._synthesize(transcript, system_rules)
        summary = self._understand(body)
        related = self.retriever.search(summary or body, k=5)
        decision = self._normalize_decision(self._decide(body, summary, related), related)
        decision = self._apply_hint_path(decision, hint_path)
        # 归档果断落库，不因 ambiguous 打断用户
        if decision.ambiguous:
            decision = PlacementDecision(
                action="new",
                rel_path=decision.rel_path,
                title=decision.title,
                category=decision.category,
                tags=decision.tags,
                ambiguous=False,
                reason=decision.reason or "会话归档",
            )
        self._apply(decision, body, conversation_id=conversation_id)
        return IngestResult(
            status="saved",
            rel_path=decision.rel_path,
            question_id=None,
            message=f"已归档到 {decision.rel_path}",
        )

    def _synthesize(self, transcript: str, system_rules: str) -> str:
        rules = system_rules.strip() or _DEFAULT_SUMMARY_RULES
        messages = [
            {
                "role": "system",
                "content": (
                    "你是知识库编辑，负责把一整段会话归档成一篇结构清晰、可长期查阅的文档。\n"
                    "务必遵守下列规约（尤其是会话总结/归档部分）：\n\n" + rules
                ),
            },
            {
                "role": "user",
                "content": (
                    "以下是完整会话记录。请通读全部内容后，产出一篇归档文档的正文：\n"
                    "- 按主题而非发言顺序组织，跨轮去重合并，冲突以更新信息为准\n"
                    "- 剥离对话痕迹，只保留结论与事实，保留可核验的来源\n"
                    "- 只输出正文 Markdown，不要 frontmatter，不要用代码围栏包裹全文\n\n"
                    f"=== 会话记录 ===\n{transcript}"
                ),
            },
        ]
        body = self.llm.chat(messages, big=True).strip()
        if not body.endswith("\n"):
            body += "\n"
        return body

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

    def resolve_agent_choices(
        self,
        qid: str,
        choice_ids: list[str],
        *,
        conversation_context: str = "",
    ) -> IngestResult:
        q = self.pending.get(qid)
        options = {o["id"]: o["label"] for o in q["options"]}
        labels = [options[cid] for cid in choice_ids if cid in options]
        if not labels:
            return IngestResult(
                status="rejected",
                rel_path=None,
                question_id=qid,
                message="未选择有效选项",
            )
        payload = q.get("payload", {})
        context = payload.get("context", "")
        self.pending.resolve_many(qid, choice_ids)

        if payload.get("kind") == "agent":
            if choice_ids == ["done"]:
                written_path = payload.get("written_path") or self._extract_written_path(
                    context
                )
                if written_path:
                    return IngestResult(
                        status="saved",
                        rel_path=written_path,
                        question_id=None,
                        message=f"已记录到 {written_path}",
                    )
                return IngestResult(
                    status="acknowledged",
                    rel_path=None,
                    question_id=None,
                    message="好的，已确认。",
                )
            parts = [f"用户确认选择：{'、'.join(labels)}"]
            if conversation_context.strip():
                parts.append(f"\n对话上下文：\n{conversation_context.strip()}")
            if context:
                parts.append(f"\n背景：{context}")
            parts.append(
                "\n请结合以上对话与选择，继续完成知识库整理（必要时调用 write_kb）。"
            )
            return IngestResult(
                status="continue",
                rel_path=None,
                question_id=None,
                message="正在根据你的选择继续处理…",
                continue_prompt="\n".join(parts),
            )

        text = "用户希望记录以下内容：\n" + "\n".join(f"- {label}" for label in labels)
        if conversation_context.strip():
            text += f"\n\n对话上下文：\n{conversation_context.strip()}"
        if context:
            text += f"\n\n背景：{context}"
        return self.ingest_text(text)

    def _reorganize(self, existing_body: str, new_content: str, title: str) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是知识库文档编辑。将已有文档与新内容合并，输出一份完整、结构清晰的 Markdown 正文。\n"
                    "要求：\n"
                    "1. 先通读已有文档与新内容的全部信息，去重、归类，不要简单拼接\n"
                    "2. 形成完整文档：标题层级合理、章节有序、信息不遗漏\n"
                    "3. 删除对话痕迹（如「帮我记录」「用户希望记录」等元叙述），保留事实\n"
                    "4. 若新内容修正或补充旧内容，以新内容为准\n"
                    "5. 只输出正文 Markdown，不要 frontmatter，不要用代码围栏包裹全文"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"文档标题参考：{title}\n\n"
                    f"=== 已有文档 ===\n{existing_body}\n\n"
                    f"=== 待合并的新内容 ===\n{new_content}"
                ),
            },
        ]
        body = self.llm.chat(messages, big=True).strip()
        if not body.endswith("\n"):
            body += "\n"
        return body

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

    @staticmethod
    def _extract_written_path(context: str) -> str | None:
        if not context:
            return None
        match = re.search(r"保存在\s+(\S+?)(?:\s|$|[，。])", context)
        return match.group(1) if match else None

    def _apply_hint_path(
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

    def _apply(
        self,
        decision: PlacementDecision,
        content: str,
        *,
        conversation_id: str | None = None,
    ) -> None:
        rel_path = decision.rel_path
        exists = False
        try:
            self.repo.read_doc(rel_path)
            exists = True
        except FileNotFoundError:
            exists = False

        if decision.action in ("merge", "append") and exists:
            doc = self.repo.read_doc(rel_path)
            merged_meta = {**doc.meta, "title": decision.title or doc.meta.get("title", "")}
            if decision.tags:
                existing_tags = doc.meta.get("tags") or []
                merged_meta["tags"] = list(dict.fromkeys(existing_tags + decision.tags))
            if conversation_id:
                merged_meta["conversation_id"] = conversation_id
                merged_meta["source"] = "conversation"
            body = self._reorganize(doc.body, content, decision.title)
            self.repo.write_doc(
                rel_path,
                meta=merged_meta,
                body=body,
                commit_msg=f"merge: 整理合并 {rel_path}",
            )
            verb = "整理合并到"
        else:
            meta: dict = {
                "title": decision.title,
                "tags": decision.tags,
                "source": "conversation" if conversation_id else "chat",
            }
            if conversation_id:
                meta["conversation_id"] = conversation_id
            self.repo.write_doc(
                rel_path,
                meta=meta,
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
