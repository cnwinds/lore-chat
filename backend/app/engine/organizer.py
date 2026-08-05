from __future__ import annotations


import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.config import Settings

from app.engine.conversations import ConversationStore
from app.storage.repo import KnowledgeRepo
from app.engine.placement import PlacementDecision, PlacementPlanner
from app.engine.intent import is_question_only
from app.engine.merge_sessions import MergeSessionStore
from app.engine.retriever import Retriever
from app.engine.pending import PendingStore
from app.engine.document_synthesis import DocumentSynthesis
from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.merge_workflow import MergeResult, MergeWorkflow
from app.engine.write_policy import WriteMode, resolve_write_mode
from app.models.llm import LLMClient


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
        pending: PendingStore,
        llm: LLMClient,
        knowledge_writer: KnowledgeWriter,
        settings: Settings | None = None,
        merge_workflow: MergeWorkflow | None = None,
        planner: PlacementPlanner | None = None,
    ):
        self.repo = repo
        self.retriever = retriever
        self.pending = pending
        self.llm = llm
        self.settings = settings or Settings()
        self.writer = knowledge_writer
        self.synthesis = DocumentSynthesis(llm)
        self.planner = planner or PlacementPlanner(repo, retriever, llm)
        self.merge = merge_workflow or MergeWorkflow(
            repo=repo,
            retriever=retriever,
            llm=llm,
            writer=knowledge_writer,
            planner=self.planner,
            pending=pending,
            synthesis=self.synthesis,
        )

    def ingest_text(
        self,
        content: str,
        *,
        forced_rel_path: str,
        write_mode: WriteMode = "auto",
        conversation_id: str | None = None,
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
        mode = resolve_write_mode(decision.rel_path, write_mode)
        self._apply(
            decision, content, conversation_id=conversation_id, write_mode=mode
        )
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
            body = self.synthesis.archive_transcript(transcript, system_rules)
        else:
            segments = list(
                ConversationStore.iter_transcript_segments(
                    conv, max_chars=self.settings.summarize_segment_chars
                )
            )
            partials = [
                self.synthesis.archive_segment(seg["text"], system_rules, seg)
                for seg in segments
            ]
            body = self.synthesis.merge_archive_segments(partials, system_rules)
        if not (forced_rel_path or "").strip():
            return IngestResult(
                status="rejected",
                rel_path=None,
                question_id=None,
                message="归档必须指定 directory 与 filename（由工具参数拼成目标路径）。",
            )
        decision = self.planner.decision_for_forced_path(forced_rel_path)
        # 归档正文已是完整终稿，覆盖目标路径，避免再与旧稿 LLM 合并
        self._apply(
            decision, body, conversation_id=conversation_id, write_mode="replace"
        )
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
        return self.merge.merge_documents(
            source_paths,
            instruction=instruction,
            order=order,
            target_path=target_path,
            title_hint=title_hint,
            merge_sessions=merge_sessions,
            session_id=session_id,
        )

    def regenerate_merge(
        self, merge_id: str, *, merge_sessions: MergeSessionStore
    ) -> MergeResult:
        return self.merge.regenerate_merge(merge_id, merge_sessions=merge_sessions)

    def reject_merge(self, merge_id: str, *, merge_sessions: MergeSessionStore) -> MergeResult:
        return self.merge.reject_merge(merge_id, merge_sessions=merge_sessions)

    def accept_merge(self, merge_id: str, *, merge_sessions: MergeSessionStore) -> MergeResult:
        return self.merge.accept_merge(merge_id, merge_sessions=merge_sessions)

    def resolve_merge_sources(
        self,
        merge_id: str,
        delete_paths: list[str],
        *,
        merge_sessions: MergeSessionStore,
    ) -> MergeResult:
        return self.merge.resolve_merge_sources(
            merge_id, delete_paths, merge_sessions=merge_sessions
        )

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
        write_mode: WriteMode = "merge",
    ) -> None:
        rel_path = decision.rel_path
        exists = False
        try:
            self.repo.read_doc(rel_path)
            exists = True
        except FileNotFoundError:
            exists = False

        body = content if content.endswith("\n") else f"{content}\n"

        if write_mode == "replace" and exists:
            doc = self.repo.read_doc(rel_path)
            meta = {
                **doc.meta,
                "title": decision.title or doc.meta.get("title", ""),
            }
            if decision.tags:
                existing_tags = doc.meta.get("tags") or []
                meta["tags"] = list(dict.fromkeys(existing_tags + decision.tags))
            meta = _conversation_ids_meta(meta, conversation_id)
            self.writer.persist_document(
                rel_path,
                meta,
                body,
                commit_msg=f"replace: {rel_path}",
                changelog_line=f"覆盖写入 {rel_path}：{decision.reason or decision.title}",
            )
            return

        if write_mode == "merge" and decision.action in ("merge", "append") and exists:
            doc = self.repo.read_doc(rel_path)
            merged_meta = {
                **doc.meta,
                "title": decision.title or doc.meta.get("title", ""),
            }
            if decision.tags:
                existing_tags = doc.meta.get("tags") or []
                merged_meta["tags"] = list(
                    dict.fromkeys(existing_tags + decision.tags)
                )
            merged_meta = _conversation_ids_meta(merged_meta, conversation_id)
            merged_body = self.synthesis.reorganize_existing(
                doc.body, content, decision.title
            )
            self.writer.persist_document(
                rel_path,
                merged_meta,
                merged_body,
                commit_msg=f"merge: 整理合并 {rel_path}",
                changelog_line=f"整理合并到 {rel_path}：{decision.reason or decision.title}",
            )
            return

        meta: dict = {
            "title": decision.title,
            "tags": decision.tags,
            "source": "conversation" if conversation_id else "chat",
        }
        meta = _conversation_ids_meta(meta, conversation_id)
        self.writer.persist_document(
            rel_path,
            meta,
            body,
            commit_msg=f"add: 新建 {rel_path}",
            changelog_line=f"创建 {rel_path}：{decision.reason or decision.title}",
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
                "\n请结合以上对话与选择，继续完成知识库整理（必要时先 list_kb_structure，再 write_kb）。"
            )
            return IngestResult(
                status="continue",
                rel_path=None,
                question_id=None,
                message="正在根据你的选择继续处理…",
                continue_prompt="\n".join(parts),
            )

        if not payload.get("kind"):
            return IngestResult(
                status="saved",
                rel_path=None,
                question_id=None,
                message=f"已确认：{'、'.join(labels)}",
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
