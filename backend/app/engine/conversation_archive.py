"""会话归档：通读 transcript → 合成终稿 → 强制路径落库。"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.engine.conversation.transcript import ConversationTranscript
from app.engine.document_synthesis import DocumentSynthesis
from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.memory.constants import (
    MEMORY_FILE_DISABLED_MSG,
    is_memory_projection_path,
)
from app.engine.placement import PlacementPlanner
from app.models.llm import LLMClient
from app.storage.repo import KnowledgeRepo


@dataclass
class ArchiveResult:
    status: str
    rel_path: str | None
    question_id: str | None
    message: str
    continue_prompt: str | None = None
    sandbox_run_args: dict | None = None


class ConversationArchiveWorkflow:
    """整段会话归档（非逐轮拼接）。"""

    def __init__(
        self,
        *,
        repo: KnowledgeRepo,
        llm: LLMClient,
        writer: KnowledgeWriter,
        planner: PlacementPlanner,
        settings: Settings | None = None,
        synthesis: DocumentSynthesis | None = None,
    ):
        self.repo = repo
        self.llm = llm
        self.writer = writer
        self.planner = planner
        self.settings = settings or Settings()
        self.synthesis = synthesis or DocumentSynthesis(llm)

    def summarize(
        self,
        transcript: str,
        *,
        conv: dict | None = None,
        forced_rel_path: str,
        system_rules: str = "",
        conversation_id: str | None = None,
    ) -> ArchiveResult:
        if not transcript.strip():
            return ArchiveResult(
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
                ConversationTranscript.iter_segments(
                    conv, max_chars=self.settings.summarize_segment_chars
                )
            )
            partials = [
                self.synthesis.archive_segment(seg["text"], system_rules, seg)
                for seg in segments
            ]
            body = self.synthesis.merge_archive_segments(partials, system_rules)
        if not (forced_rel_path or "").strip():
            return ArchiveResult(
                status="rejected",
                rel_path=None,
                question_id=None,
                message="归档必须指定 directory 与 filename（由工具参数拼成目标路径）。",
            )
        if is_memory_projection_path(forced_rel_path):
            return ArchiveResult(
                status="rejected",
                rel_path=None,
                question_id=None,
                message=MEMORY_FILE_DISABLED_MSG,
            )
        decision = self.planner.decision_for_forced_path(forced_rel_path)
        # 归档正文已是完整终稿，覆盖目标路径，避免再与旧稿 LLM 合并
        self.writer.apply_placement(
            decision,
            body,
            write_mode="replace",
            conversation_id=conversation_id,
            reorganize_existing=self.synthesis.reorganize_existing,
        )
        return ArchiveResult(
            status="saved",
            rel_path=decision.rel_path,
            question_id=None,
            message=f"已归档到 {decision.rel_path}",
        )
