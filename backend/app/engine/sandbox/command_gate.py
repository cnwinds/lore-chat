"""沙箱高风险命令确认门：创建 Pending + 解析 approve/deny。

与 Organizer（KB 摄入）解耦；批准后由 PendingResolver 代跑 sandbox_run。
"""

from __future__ import annotations

from app.engine.organizer import IngestResult
from app.engine.pending import PendingStore
from app.engine.sandbox.policy import command_needs_confirmation

CONFIRM_OPTIONS = [
    {"id": "approve", "label": "执行"},
    {"id": "deny", "label": "取消"},
]


class SandboxCommandGate:
    def __init__(
        self,
        pending: PendingStore | None = None,
        *,
        trust_mode: bool = True,
    ) -> None:
        self.pending = pending
        self.trust_mode = trust_mode

    def maybe_confirm(self, args: dict, command: str) -> dict | None:
        """需要确认时返回 ask_user 形态结果；否则 None。"""
        if self.trust_mode or bool(args.get("confirmed")):
            return None
        if not command_needs_confirmation(command):
            return None
        if self.pending is None:
            return {
                "summary": "该命令需要确认，但 PendingStore 不可用",
                "sources": [],
                "error": "pending unavailable",
            }
        cwd = (args.get("cwd") or "/workspace").strip() or "/workspace"
        background = bool(args.get("background", False))
        timeout = args.get("timeout_sec")
        timeout_sec = float(timeout) if timeout is not None else None
        qid = self.pending.create(
            f"是否在沙箱执行此命令？\n\n```\n{command}\n```\ncwd={cwd}",
            list(CONFIRM_OPTIONS),
            {
                "kind": "sandbox_confirm",
                "command": command,
                "cwd": cwd,
                "background": background,
                "timeout_sec": timeout_sec,
            },
        )
        return {
            "summary": "等待用户确认是否执行沙箱命令",
            "sources": [],
            "question_id": qid,
            "question": f"是否在沙箱执行？\n{command}",
            "options": list(CONFIRM_OPTIONS),
            "awaiting_user": True,
        }

    def resolve(self, qid: str, choice_ids: list[str]) -> IngestResult:
        """解析 sandbox_confirm；approve 返回 sandbox_execute + run_args。"""
        if self.pending is None:
            return IngestResult(
                status="rejected",
                rel_path=None,
                question_id=qid,
                message="PendingStore 不可用",
            )
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
        if payload.get("kind") != "sandbox_confirm":
            return IngestResult(
                status="rejected",
                rel_path=None,
                question_id=qid,
                message="不是沙箱确认问题",
            )
        self.pending.resolve_many(qid, choice_ids)

        if "deny" in choice_ids or choice_ids == ["deny"]:
            return IngestResult(
                status="acknowledged",
                rel_path=None,
                question_id=None,
                message="已取消沙箱命令。",
            )
        if "approve" not in choice_ids:
            return IngestResult(
                status="rejected",
                rel_path=None,
                question_id=qid,
                message="未选择有效选项",
            )
        command = payload.get("command") or ""
        cwd = payload.get("cwd") or "/workspace"
        background = bool(payload.get("background", False))
        timeout_sec = payload.get("timeout_sec")
        run_args: dict = {
            "command": command,
            "cwd": cwd,
            "background": background,
            "confirmed": True,
        }
        if timeout_sec is not None:
            run_args["timeout_sec"] = timeout_sec
        return IngestResult(
            status="sandbox_execute",
            rel_path=None,
            question_id=None,
            message="正在按你的批准执行沙箱命令…",
            sandbox_run_args=run_args,
        )


__all__ = ["SandboxCommandGate", "CONFIRM_OPTIONS"]
