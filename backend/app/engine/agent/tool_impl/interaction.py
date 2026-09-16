from __future__ import annotations

from app.engine.agent.ask_user_options import normalize_ask_options
from app.engine.pending import PendingStore


class InteractionTools:
    def __init__(self, pending: PendingStore, conversations=None) -> None:
        self.pending = pending
        self.conversations = conversations

    def ask_user(
        self,
        args: dict,
        conversation_id: str | None = None,
        responding_role_id: str | None = None,
    ) -> dict:
        question = args["question"]
        options = normalize_ask_options(args.get("options"))
        multi_select = bool(args.get("multi_select", False))
        payload = {
            "kind": "agent",
            "context": args.get("context", ""),
            **(args.get("payload") or {}),
        }
        cid = (conversation_id or "").strip()
        if cid:
            payload["conversation_id"] = cid
        rid = (responding_role_id or "").strip()
        if not rid and cid and self.conversations is not None:
            try:
                rid = (self.conversations.get_responding_role_id(cid) or "").strip()
            except KeyError:
                rid = ""
        if rid:
            payload["responding_role_id"] = rid
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
