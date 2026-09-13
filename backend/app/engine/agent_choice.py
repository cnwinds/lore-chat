"""Agent / 录入征询选项 → IngestResult。

续聊时 continue_prompt 只带所选选项文案；对话历史由同一会话的 llm_history 提供。
"""

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
        choice_text = "、".join(labels)

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
            return ChoiceResult(
                status="continue",
                rel_path=None,
                question_id=None,
                message="正在根据你的选择继续处理…",
                continue_prompt=choice_text,
            )

        if not payload.get("kind"):
            return ChoiceResult(
                status="saved",
                rel_path=None,
                question_id=None,
                message=f"已确认：{choice_text}",
            )

        return ChoiceResult(
            status="continue",
            rel_path=None,
            question_id=None,
            message="请按目录规划写入知识库。",
            continue_prompt=choice_text,
        )
