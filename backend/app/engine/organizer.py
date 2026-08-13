from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.config import Settings

from app.storage.repo import KnowledgeRepo
from app.engine.placement import PlacementDecision, PlacementPlanner
from app.engine.intent import is_question_only
from app.engine.merge_sessions import MergeSessionStore
from app.engine.retriever import Retriever
from app.engine.pending import PendingStore
from app.engine.document_synthesis import DocumentSynthesis
from app.engine.knowledge_writer import KnowledgeWriter, sanitize_doc_meta
from app.engine.agent_choice import AgentChoiceResolution
from app.engine.conversation_archive import ConversationArchiveWorkflow
from app.engine.merge_workflow import MergeResult, MergeWorkflow
from app.engine.memory.constants import is_memory_projection_path
from app.engine.write_policy import WriteMode, resolve_write_mode
from app.models.llm import LLMClient

_MEMORY_FILE_DISABLED_MSG = (
    "记忆已改由数据库管理，请到设置 → 记忆中编辑，或使用 manage_memory"
)


@dataclass
class IngestResult:
    status: str
    rel_path: str | None
    question_id: str | None
    message: str
    continue_prompt: str | None = None
    # 沙箱确认：由 SandboxCommandGate 填充；PendingResolver 代跑
    sandbox_run_args: dict | None = None


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
        archive_workflow: ConversationArchiveWorkflow | None = None,
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
        self.archive = archive_workflow or ConversationArchiveWorkflow(
            repo=repo,
            llm=llm,
            writer=knowledge_writer,
            planner=self.planner,
            settings=self.settings,
            synthesis=self.synthesis,
        )
        self.choices = AgentChoiceResolution(pending)

    def ingest_text(
        self,
        content: str,
        *,
        forced_rel_path: str,
        write_mode: WriteMode = "auto",
        conversation_id: str | None = None,
        meta: dict | None = None,
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
                message="缺少目标路径。请通过 write_doc 指定 directory 与 filename。",
            )
        if is_memory_projection_path(forced_rel_path):
            return IngestResult(
                status="rejected",
                rel_path=None,
                question_id=None,
                message=_MEMORY_FILE_DISABLED_MSG,
            )

        decision = self.planner.decision_for_forced_path(forced_rel_path)
        clean = sanitize_doc_meta(meta)
        if clean.get("title"):
            decision.title = clean["title"]
        if "tags" in clean:
            decision.tags = list(clean["tags"])
        mode = resolve_write_mode(decision.rel_path, write_mode)
        self._apply(
            decision,
            content,
            conversation_id=conversation_id,
            write_mode=mode,
            meta_overrides=clean or None,
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
        r = self.archive.summarize(
            transcript,
            conv=conv,
            forced_rel_path=forced_rel_path,
            system_rules=system_rules,
            conversation_id=conversation_id,
        )
        return IngestResult(
            status=r.status,
            rel_path=r.rel_path,
            question_id=r.question_id,
            message=r.message,
            continue_prompt=r.continue_prompt,
            sandbox_run_args=r.sandbox_run_args,
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

    def _apply(
        self,
        decision: PlacementDecision,
        content: str,
        *,
        conversation_id: str | None = None,
        write_mode: WriteMode = "merge",
        meta_overrides: dict | None = None,
    ) -> None:
        self.writer.apply_placement(
            decision,
            content,
            write_mode=write_mode,
            conversation_id=conversation_id,
            reorganize_existing=self.synthesis.reorganize_existing,
            meta_overrides=meta_overrides,
        )

    def resolve_agent_choices(
        self,
        qid: str,
        choice_ids: list[str],
        *,
        conversation_context: str = "",
    ) -> IngestResult:
        r = self.choices.resolve(
            qid, choice_ids, conversation_context=conversation_context
        )
        return IngestResult(
            status=r.status,
            rel_path=r.rel_path,
            question_id=r.question_id,
            message=r.message,
            continue_prompt=r.continue_prompt,
            sandbox_run_args=r.sandbox_run_args,
        )

