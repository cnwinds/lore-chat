"""Agent / 录入征询选项 → IngestResult（continue_prompt 拼装）。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.engine.pending import PendingStore


@dataclass
class ChoiceResult:
    status: str
    rel_path: str | None
    question_id: str | None
    message: str
    continue_prompt: str | None = None
    sandbox_run_args: dict | None = None


class AgentChoiceResolution:
    """Pending 选项决议（非 sandbox_confirm；沙箱走 SandboxCommandGate）。"""

    def __init__(self, pending: PendingStore):
        self.pending = pending

    @staticmethod
    def extract_written_path(context: str) -> str | None:
        if not context:
            return None
        match = re.search(r"保存在\s+(\S+?)(?:\s|$|[，。])", context)
        return match.group(1) if match else None

    def resolve(
        self,
        qid: str,
        choice_ids: list[str],
        *,
        conversation_context: str = "",
    ) -> ChoiceResult:
        q = self.pending.get(qid)
        payload = q.get("payload", {})
        if payload.get("kind") == "sandbox_confirm":
            return ChoiceResult(
                status="rejected",
                rel_path=None,
                question_id=qid,
                message="沙箱确认请经 SandboxCommandGate 决议",
            )
        options = {o["id"]: o["label"] for o in q["options"]}
        labels = [options[cid] for cid in choice_ids if cid in options]
        if not labels:
            return ChoiceResult(
                status="rejected",
                rel_path=None,
                question_id=qid,
                message="未选择有效选项",
            )
        context = payload.get("context", "")
        self.pending.resolve_many(qid, choice_ids)

        if payload.get("kind") == "agent":
            if choice_ids == ["done"]:
                written_path = payload.get("written_path") or self.extract_written_path(
                    context
                )
                if written_path:
                    return ChoiceResult(
                        status="saved",
                        rel_path=written_path,
                        question_id=None,
                        message=f"已记录到 {written_path}",
                    )
                return ChoiceResult(
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
                "\n请结合以上对话与选择，继续完成知识库整理（必要时先 list_kb_structure，再 write_doc）。"
            )
            return ChoiceResult(
                status="continue",
                rel_path=None,
                question_id=None,
                message="正在根据你的选择继续处理…",
                continue_prompt="\n".join(parts),
            )

        if not payload.get("kind"):
            return ChoiceResult(
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
            "\n请先调用 list_kb_structure 查看目录，再调用 write_doc（必填 directory、filename、text）写入；"
            "禁止无路径自动落库。"
        )
        return ChoiceResult(
            status="continue",
            rel_path=None,
            question_id=None,
            message="请按目录规划写入知识库。",
            continue_prompt="\n".join(parts),
        )
