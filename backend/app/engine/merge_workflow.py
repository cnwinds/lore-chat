from __future__ import annotations

from dataclasses import dataclass

from app.engine.content_hash import body_hash
from app.engine.document_synthesis import DocumentSynthesis
from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.merge_sessions import MergeSessionStore
from app.engine.pending import PendingStore
from app.engine.placement import PlacementDecision, PlacementPlanner
from app.engine.retriever import Retriever
from app.models.llm import LLMClient
from app.storage.repo import KnowledgeRepo


@dataclass
class MergeResult:
    status: str
    merge_id: str | None
    rel_path: str | None
    source_paths: list[str]
    user_modified: bool
    question_id: str | None
    message: str


class MergeWorkflow:
    """多文档合并：合成、落库、审阅会话与源文档清理。"""

    def __init__(
        self,
        *,
        repo: KnowledgeRepo,
        retriever: Retriever,
        llm: LLMClient,
        writer: KnowledgeWriter,
        planner: PlacementPlanner,
        pending: PendingStore,
        synthesis: DocumentSynthesis | None = None,
    ):
        self.repo = repo
        self.retriever = retriever
        self.llm = llm
        self.writer = writer
        self.planner = planner
        self.pending = pending
        self.synthesis = synthesis or DocumentSynthesis(llm)

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

    def _synthesize_merge(self, sources: list[tuple[str, str]], instruction: str) -> str:
        return self.synthesis.merge_documents(sources, instruction)


__all__ = ["MergeResult", "MergeWorkflow"]
