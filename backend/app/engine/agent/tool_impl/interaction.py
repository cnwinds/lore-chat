from __future__ import annotations

from app.engine.pending import PendingStore


class InteractionTools:
    def __init__(self, pending: PendingStore) -> None:
        self.pending = pending

    def ask_user(self, args: dict) -> dict:
        question = args["question"]
        options = args["options"]
        multi_select = bool(args.get("multi_select", False))
        payload = {
            "kind": "agent",
            "context": args.get("context", ""),
            **(args.get("payload") or {}),
        }
        qid = self.pending.create(
            question, options, payload, multi_select=multi_select
        )
        return {
            "summary": "等待用户选择",
            "sources": [],
            "question_id": qid,
            "question": question,
            "options": options,
            "multi_select": multi_select,
            "awaiting_user": True,
        }
