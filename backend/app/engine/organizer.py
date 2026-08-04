from __future__ import annotations


import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.config import Settings

from app.engine.conversations import ConversationStore
from app.engine.content_hash import body_hash
from app.storage.repo import KnowledgeRepo
from app.engine.placement import PlacementDecision, PlacementPlanner
from app.engine.intent import is_question_only
from app.engine.merge_sessions import MergeSessionStore
from app.engine.retriever import Retriever
from app.engine.pending import PendingStore
from app.engine.knowledge_writer import KnowledgeWriter
from app.index.indexer import Indexer
from app.models.llm import LLMClient


# 仅当《戒律》缺失/读取失败时的兜底规则；正常运行以 system_rules（《戒律》二）为准。
_DEFAULT_SUMMARY_RULES = (
    "1. 总结对象是整段会话，先通读全部对话与依据再动笔。\n"
    "2. 全局重构、禁止流水线拼接：按主题而非发言/来源顺序组织；跨轮去重合并；"
    "禁止用 --- 堆叠多个一级标题，全篇只有一套自洽的标题层级。\n"
    "3. 剥离对话痕迹（如「帮我记录」「用户说」），只留结论与事实。\n"
    "4. 保留可核验性：事实、数据、版本、链接等须有出处，不臆造、不补全。"
)


@dataclass
class IngestResult:
    status: str
    rel_path: str | None
    question_id: str | None
    message: str
    continue_prompt: str | None = None


@dataclass
class MergeResult:
    status: str
    merge_id: str | None
    rel_path: str | None
    source_paths: list[str]
    user_modified: bool
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
        knowledge_writer: KnowledgeWriter,
        settings: Settings | None = None,
    ):
        self.repo = repo
        self.retriever = retriever
        self.pending = pending
        self.llm = llm
        self.settings = settings or Settings()
        self.writer = knowledge_writer
        self.planner = PlacementPlanner(repo, retriever, llm)

    def ingest_text(
        self,
        content: str,
        *,
        forced_rel_path: str,
    ) -> IngestResult:
        if is_question_only(content):
            return IngestResult(
                status="rejected",
                rel_path=None,
                question_id=None,
                message="这是提问而非资料，未写入知识库。",
            )

        if not (forced_rel_path or "").strip():
            return IngestResult(
                status="rejected",
                rel_path=None,
                question_id=None,
                message="缺少目标路径。请通过 write_kb 指定 directory 与 filename。",
            )

        decision = self.planner.decision_for_forced_path(forced_rel_path)
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
        conv: dict | None = None,
        forced_rel_path: str,
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
        if conv is None:
            conv = {"messages": []}
        if len(transcript) <= self.settings.summarize_segment_chars:
            body = self._synthesize(transcript, system_rules)
        else:
            segments = list(
                ConversationStore.iter_transcript_segments(
                    conv, max_chars=self.settings.summarize_segment_chars
                )
            )
            partials = [
                self._synthesize_segment(seg["text"], system_rules, seg) for seg in segments
            ]
            body = self._synthesize_merge_segments(partials, system_rules)
        if not (forced_rel_path or "").strip():
            return IngestResult(
                status="rejected",
                rel_path=None,
                question_id=None,
                message="归档必须指定 directory 与 filename（由工具参数拼成目标路径）。",
            )
        decision = self.planner.decision_for_forced_path(forced_rel_path)
        self._apply(decision, body, conversation_id=conversation_id)
        return IngestResult(
            status="saved",
            rel_path=decision.rel_path,
            question_id=None,
            message=f"已归档到 {decision.rel_path}",
        )

    def merge_documents(
        self,
        source_paths: list[str],
        *,
        instruction: str = "",
        order: list[str] | None = None,
        target_path: str | None = None,
        title_hint: str | None = None,
        merge_sessions: MergeSessionStore,
        session_id: str | None = None,
    ) -> MergeResult:
        if len(source_paths) < 2:
            return MergeResult(
                status="rejected",
                merge_id=None,
                rel_path=None,
                source_paths=list(source_paths),
                user_modified=False,
                question_id=None,
                message="至少需要 2 篇文档才能合并。",
            )

        ordered = [p for p in (order or []) if p in source_paths]
        for rel in source_paths:
            if rel not in ordered:
                ordered.append(rel)

        sources: list[tuple[str, str]] = []
        for rel in ordered:
            if self.repo.is_protected(rel):
                return MergeResult(
                    status="rejected",
                    merge_id=None,
                    rel_path=None,
                    source_paths=list(source_paths),
                    user_modified=False,
                    question_id=None,
                    message=f"包含系统保护路径，拒绝合并：{rel}",
                )
            try:
                doc = self.repo.read_doc(rel)
            except FileNotFoundError:
                return MergeResult(
                    status="rejected",
                    merge_id=None,
                    rel_path=None,
                    source_paths=list(source_paths),
                    user_modified=False,
                    question_id=None,
                    message=f"文档不存在：{rel}",
                )
            sources.append((rel, doc.body))

        merged_body = self._synthesize_merge(sources, instruction)
        summary = self.planner.understand(merged_body)
        related = self.retriever.search(summary or merged_body, k=5).hits
        decision = self.planner.normalize_decision(
            self.planner.decide(merged_body, summary, related), related
        )
        generated_hash = body_hash(merged_body)

        if title_hint:
            decision = PlacementDecision(
                action=decision.action,
                rel_path=decision.rel_path,
                title=title_hint,
                category=decision.category,
                tags=decision.tags,
                ambiguous=decision.ambiguous,
                reason=decision.reason,
            )
        if target_path:
            decision = PlacementDecision(
                action="new",
                rel_path=target_path,
                title=decision.title,
                category=decision.category,
                tags=decision.tags,
                ambiguous=False,
                reason=decision.reason or f"按指定路径写入 {target_path}",
            )
        else:
            decision = PlacementDecision(
                action="new",
                rel_path=decision.rel_path,
                title=decision.title,
                category=decision.category,
                tags=decision.tags,
                ambiguous=False,
                reason=decision.reason,
            )

        self.writer.persist_document(
            decision.rel_path,
            {
                "title": decision.title,
                "tags": decision.tags,
                "source": "merge",
                "merged_from": list(source_paths),
            },
            merged_body,
            commit_msg=f"merge: 生成合并文档 {decision.rel_path}",
            changelog_line=f"创建 {decision.rel_path}：{decision.reason or decision.title}",
        )
        doc = self.repo.read_doc(decision.rel_path)
        merge_id = session_id
        user_modified = False
        if merge_id:
            try:
                prev = merge_sessions.get(merge_id)
            except KeyError:
                merge_id = None
            else:
                prev_path = prev.get("new_path")
                if prev_path:
                    try:
                        user_modified = merge_sessions.user_modified(
                            merge_id, self.repo.read_doc(prev_path).body
                        )
                    except FileNotFoundError:
                        user_modified = False
                merge_sessions.update(
                    merge_id,
                    status="pending_review",
                    new_path=decision.rel_path,
                    source_paths=list(source_paths),
                    instruction=instruction,
                    order=ordered,
                    generated_content_hash=generated_hash,
                )
        if not merge_id:
            merge_id = merge_sessions.create(
                new_path=decision.rel_path,
                source_paths=list(source_paths),
                instruction=instruction,
                order=ordered,
                generated_content_hash=generated_hash,
            )

        return MergeResult(
            status="saved",
            merge_id=merge_id,
            rel_path=decision.rel_path,
            source_paths=list(source_paths),
            user_modified=user_modified,
            question_id=None,
            message=f"已合并保存到 {decision.rel_path}",
        )

    def regenerate_merge(
        self, merge_id: str, *, merge_sessions: MergeSessionStore
    ) -> MergeResult:
        session = merge_sessions.get(merge_id)
        if session.get("status") != "pending_review":
            return MergeResult(
                status="rejected",
                merge_id=merge_id,
                rel_path=session.get("new_path"),
                source_paths=list(session.get("source_paths", [])),
                user_modified=False,
                question_id=None,
                message="仅 pending_review 状态可重新生成。",
            )
        return self.merge_documents(
            list(session.get("source_paths", [])),
            instruction=session.get("instruction", ""),
            order=session.get("order"),
            target_path=session.get("new_path"),
            merge_sessions=merge_sessions,
            session_id=merge_id,
        )

    def reject_merge(self, merge_id: str, *, merge_sessions: MergeSessionStore) -> MergeResult:
        session = merge_sessions.get(merge_id)
        if session.get("status") != "pending_review":
            return MergeResult(
                status="rejected",
                merge_id=merge_id,
                rel_path=session.get("new_path"),
                source_paths=list(session.get("source_paths", [])),
                user_modified=False,
                question_id=None,
                message="仅 pending_review 状态可拒绝。",
            )
        rel_path = session.get("new_path")
        if rel_path:
            deleted: list[str] = []
            try:
                deleted = self.repo.delete_path(
                    rel_path, commit_msg=f"merge: 拒绝并删除 {rel_path}"
                )
            except (FileNotFoundError, ValueError):
                pass
            if deleted:
                self.writer.drop_from_index(deleted)
                self.writer.record_deletion(rel_path, deleted)
        merge_sessions.update(merge_id, status="rejected")
        return MergeResult(
            status="rejected",
            merge_id=merge_id,
            rel_path=rel_path,
            source_paths=list(session.get("source_paths", [])),
            user_modified=False,
            question_id=None,
            message=f"已拒绝合并并删除文档 {rel_path}",
        )

    def accept_merge(self, merge_id: str, *, merge_sessions: MergeSessionStore) -> MergeResult:
        session = merge_sessions.get(merge_id)
        if session.get("status") != "pending_review":
            return MergeResult(
                status="rejected",
                merge_id=merge_id,
                rel_path=session.get("new_path"),
                source_paths=list(session.get("source_paths", [])),
                user_modified=False,
                question_id=None,
                message="仅 pending_review 状态可接受。",
            )
        new_path = session.get("new_path") or ""
        source_paths = list(session.get("source_paths", []))
        merge_sessions.update(merge_id, status="accepted")
        qid = self.pending.create(
            question=f"已保留合并文档《{new_path}》。是否删除以下源文档？",
            options=[{"id": path, "label": path} for path in source_paths],
            payload={
                "kind": "merge_sources",
                "merge_id": merge_id,
                "new_path": new_path,
                "source_paths": source_paths,
            },
            multi_select=True,
        )
        return MergeResult(
            status="saved",
            merge_id=merge_id,
            rel_path=new_path,
            source_paths=source_paths,
            user_modified=False,
            question_id=qid,
            message="已接受合并文档，请选择是否删除源文档。",
        )

    def resolve_merge_sources(
        self,
        merge_id: str,
        delete_paths: list[str],
        *,
        merge_sessions: MergeSessionStore,
    ) -> MergeResult:
        session = merge_sessions.get(merge_id)
        source_paths = list(session.get("source_paths", []))
        source_set = set(source_paths)
        invalid = [path for path in delete_paths if path not in source_set]
        if invalid:
            return MergeResult(
                status="rejected",
                merge_id=merge_id,
                rel_path=session.get("new_path"),
                source_paths=source_paths,
                user_modified=False,
                question_id=None,
                message=f"删除列表包含非源文档：{', '.join(invalid)}",
            )

        deleted: list[str] = []
        for path in delete_paths:
            if self.repo.is_protected(path):
                continue
            try:
                deleted_files = self.repo.delete_path(
                    path, commit_msg=f"merge: 删除源文档 {path}"
                )
            except (FileNotFoundError, ValueError):
                continue
            self.writer.drop_from_index(deleted_files)
            self.writer.record_deletion(path, deleted_files)
            deleted.append(path)

        if deleted:
            msg = f"已删除源文档：{', '.join(deleted)}"
        else:
            msg = "未删除任何源文档。"
        return MergeResult(
            status="saved",
            merge_id=merge_id,
            rel_path=session.get("new_path"),
            source_paths=source_paths,
            user_modified=False,
            question_id=None,
            message=msg,
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
                    "以下是完整会话记录。请严格按上述规约通读全文后产出归档文档正文；"
                    "只输出正文 Markdown，不要 frontmatter，不要用代码围栏包裹全文。\n\n"
                    f"=== 会话记录 ===\n{transcript}"
                ),
            },
        ]
        body = self.llm.chat(messages, big=True).strip()
        if not body.endswith("\n"):
            body += "\n"
        return body

    def _synthesize_segment(self, segment_text: str, system_rules: str, seg: dict) -> str:
        rules = system_rules.strip() or _DEFAULT_SUMMARY_RULES
        first_id = seg.get("first_message_id", "")
        last_id = seg.get("last_message_id", "")
        messages = [
            {
                "role": "system",
                "content": (
                    "你是知识库编辑，负责把会话片段归档成结构化摘要。\n"
                    "务必遵守下列规约：\n\n" + rules
                ),
            },
            {
                "role": "user",
                "content": (
                    f"以下是会话片段（消息 {first_id} 至 {last_id}）。"
                    "请产出该片段的摘要 Markdown，只输出正文，不要 frontmatter。\n\n"
                    f"=== 片段 ===\n{segment_text}"
                ),
            },
        ]
        body = self.llm.chat(messages, big=True).strip()
        if not body.endswith("\n"):
            body += "\n"
        return body

    def _synthesize_merge_segments(self, partials: list[str], system_rules: str) -> str:
        rules = system_rules.strip() or _DEFAULT_SUMMARY_RULES
        merged_input = "\n\n".join(
            f"=== 段摘要 {i + 1} ===\n{p}" for i, p in enumerate(partials)
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是知识库编辑，负责把多段会话摘要归并为一篇完整归档文档。\n"
                    "务必遵守下列规约：\n\n" + rules
                ),
            },
            {
                "role": "user",
                "content": (
                    "以下是按时间顺序的各段摘要。请全局重构、去重合并为终稿 Markdown；"
                    "只输出正文，不要 frontmatter。\n\n"
                    f"{merged_input}"
                ),
            },
        ]
        body = self.llm.chat(messages, big=True).strip()
        if not body.endswith("\n"):
            body += "\n"
        return body

    def _synthesize_merge(self, sources: list[tuple[str, str]], instruction: str) -> str:
        source_text = "\n\n".join(
            f"=== 文档 {path} ===\n{body}" for path, body in sources
        )
        user_instruction = instruction.strip() or "在不遗漏关键信息的前提下去重合并。"
        messages = [
            {
                "role": "system",
                "content": (
                    "你是知识库编辑，负责把多篇文档合并成一篇可长期维护的 Markdown 文档。\n"
                    "要求：\n"
                    "1. 按主题重组内容，去重并消除冲突，优先保留更新且更完整的信息\n"
                    "2. 只输出正文 Markdown，不要 frontmatter，不要使用代码围栏包裹全文\n"
                    "3. 避免对话化语言，直接给出结构化知识内容"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"合并要求：{user_instruction}\n\n"
                    "请将以下文档合并成一篇：\n\n"
                    f"{source_text}"
                ),
            },
        ]
        body = self.llm.chat(messages, big=True).strip()
        if not body.endswith("\n"):
            body += "\n"
        return body

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
                "\n请结合以上对话与选择，继续完成知识库整理（必要时先 list_kb_structure，再 write_kb）。"
            )
            return IngestResult(
                status="continue",
                rel_path=None,
                question_id=None,
                message="正在根据你的选择继续处理…",
                continue_prompt="\n".join(parts),
            )

        parts = [
            "用户通过选项确认了要记录的内容：",
            "\n".join(f"- {label}" for label in labels),
        ]
        if conversation_context.strip():
            parts.append(f"\n对话上下文：\n{conversation_context.strip()}")
        if context:
            parts.append(f"\n背景：{context}")
        parts.append(
            "\n请先调用 list_kb_structure 查看目录，再调用 write_kb（必填 directory、filename、text）写入；"
            "禁止无路径自动落库。"
        )
        return IngestResult(
            status="continue",
            rel_path=None,
            question_id=None,
            message="请按目录规划写入知识库。",
            continue_prompt="\n".join(parts),
        )

    def _reorganize(self, existing_body: str, new_content: str, title: str) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是知识库文档编辑。将已有文档与新内容合并，输出一份完整、结构清晰的 Markdown 正文。\n"
                    "要求：\n"
                    # 与会话总结规约（《戒律》二）同源；后续应考虑统一注入以免措辞漂移
                    "1. 通读已有文档与新内容，按主题去重合并，禁止简单拼接（与会话总结规约一致）\n"
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

    @staticmethod
    def _extract_written_path(context: str) -> str | None:
        if not context:
            return None
        match = re.search(r"保存在\s+(\S+?)(?:\s|$|[，。])", context)
        return match.group(1) if match else None

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
            merged_meta = _conversation_ids_meta(merged_meta, conversation_id)
            body = self._reorganize(doc.body, content, decision.title)
            self.writer.persist_document(
                rel_path,
                merged_meta,
                body,
                commit_msg=f"merge: 整理合并 {rel_path}",
                changelog_line=f"整理合并到 {rel_path}：{decision.reason or decision.title}",
            )
        else:
            meta: dict = {
                "title": decision.title,
                "tags": decision.tags,
                "source": "conversation" if conversation_id else "chat",
            }
            meta = _conversation_ids_meta(meta, conversation_id)
            self.writer.persist_document(
                rel_path,
                meta,
                f"{content}\n",
                commit_msg=f"add: 新建 {rel_path}",
                changelog_line=f"创建 {rel_path}：{decision.reason or decision.title}",
            )


def _conversation_ids_meta(meta: dict, conversation_id: str | None) -> dict:
    if not conversation_id:
        return meta
    existing = meta.get("conversation_ids")
    if isinstance(existing, list):
        ids = list(dict.fromkeys([*existing, conversation_id]))
    else:
        legacy = meta.get("conversation_id")
        ids = list(dict.fromkeys([x for x in (legacy, conversation_id) if x]))
    meta = {k: v for k, v in meta.items() if k not in ("conversation_id",)}
    meta["conversation_ids"] = ids
    meta["source"] = "conversation"
    return meta
