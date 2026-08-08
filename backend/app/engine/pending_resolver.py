from __future__ import annotations

from dataclasses import dataclass

from app.engine.conversations import ConversationStore
from app.engine.merge_sessions import MergeSessionStore
from app.engine.merge_workflow import MergeResult, MergeWorkflow
from app.engine.organizer import IngestResult, Organizer
from app.engine.pending import PendingStore


@dataclass
class PendingResolveInput:
    qid: str
    choice: str | None = None
    choices: list[str] | None = None
    conversation_id: str | None = None


class PendingResolver:
    """待决问题决议：合并源删除、Agent 多选、沙箱确认执行、会话标记。"""

    def __init__(
        self,
        *,
        pending: PendingStore,
        organizer: Organizer,
        merge_workflow: MergeWorkflow,
        conversations: ConversationStore,
        merge_sessions: MergeSessionStore,
        sandbox_tools=None,
    ):
        self.pending = pending
        self.organizer = organizer
        self.merge_workflow = merge_workflow
        self.conversations = conversations
        self.merge_sessions = merge_sessions
        self.sandbox_tools = sandbox_tools

    @staticmethod
    def _is_agent_question(q: dict) -> bool:
        payload = q.get("payload", {})
        kind = payload.get("kind")
        if kind in ("agent", "sandbox_confirm"):
            return True
        if kind == "merge_sources":
            return False
        return True

    def resolve(self, body: PendingResolveInput) -> IngestResult | MergeResult:
        try:
            q = self.pending.get(body.qid)
        except KeyError as e:
            raise KeyError(body.qid) from e

        conversation_context = ""
        if body.conversation_id:
            try:
                conv = self.conversations.get(body.conversation_id)
            except KeyError as e:
                raise ValueError("对话不存在") from e
            conversation_context = self.conversations.context_excerpt(conv)

        chosen_ids = body.choices or ([body.choice] if body.choice else [])
        chosen_labels = [
            o["label"] for o in q.get("options", []) if o.get("id") in chosen_ids
        ]
        payload = q.get("payload", {})

        if payload.get("kind") == "merge_sources":
            if not body.choices:
                raise ValueError("该问题请使用 choices 提交要删除的源文档")
            merge_id = payload.get("merge_id")
            if not merge_id:
                raise ValueError("该问题缺少 merge_id")
            self.pending.resolve_many(body.qid, body.choices)
            result = self.merge_workflow.resolve_merge_sources(
                merge_id,
                list(body.choices),
                merge_sessions=self.merge_sessions,
            )
        elif payload.get("kind") == "sandbox_confirm":
            if not chosen_ids:
                raise ValueError("请提供 choice 或 choices")
            if self.sandbox_tools is None:
                raise RuntimeError("沙箱未启用，无法决议沙箱确认")
            result = self.sandbox_tools.command_gate.resolve(body.qid, list(chosen_ids))
        elif body.choices:
            if not self._is_agent_question(q):
                raise ValueError("该问题不支持多选")
            result = self.organizer.resolve_agent_choices(
                body.qid, body.choices, conversation_context=conversation_context
            )
        elif body.choice:
            if not self._is_agent_question(q):
                raise ValueError("该问题类型已废弃，请重新发起写入")
            result = self.organizer.resolve_agent_choices(
                body.qid, [body.choice], conversation_context=conversation_context
            )
        else:
            raise ValueError("请提供 choice 或 choices")

        if body.conversation_id and chosen_labels:
            try:
                self.conversations.mark_question_resolved(
                    body.conversation_id, body.qid, "、".join(chosen_labels)
                )
            except Exception:
                pass

        return result

    async def resolve_and_apply(
        self, body: PendingResolveInput
    ) -> IngestResult | MergeResult:
        """同步决议；若为沙箱批准则直接执行命令并转为 continue。"""
        result = self.resolve(body)
        if not isinstance(result, IngestResult):
            return result
        run_args = result.sandbox_run_args
        if result.status != "sandbox_execute" or not isinstance(run_args, dict):
            return result
        if self.sandbox_tools is None:
            raise RuntimeError("沙箱未启用，无法执行已批准的命令")
        out = await self.sandbox_tools.sandbox_run(dict(run_args))
        summary = (out.get("summary") or "").strip() or "(无输出)"
        return IngestResult(
            status="continue",
            rel_path=None,
            question_id=None,
            message="沙箱命令已执行",
            continue_prompt=(
                "用户已批准，沙箱命令已在后端直接执行完毕。结果如下：\n"
                f"{summary}\n\n"
                "请根据以上输出继续任务；不要重复征询或重复执行同一命令。"
            ),
        )


__all__ = ["PendingResolver", "PendingResolveInput"]
