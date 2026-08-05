from __future__ import annotations

from app.engine.memory.constants import MEMORY_DOC_REL


class MemoryTools:
    def __init__(self, memory_service) -> None:
        self.memory_service = memory_service

    def manage_memory(self, args: dict, *, conversation_id: str | None = None) -> dict:
        del conversation_id
        if not self.memory_service:
            return {
                "summary": "记忆服务未配置",
                "sources": [],
                "ok": False,
                "error": "not_configured",
            }
        action = args.get("action")
        statement = args.get("statement", "")
        if action == "remember":
            out = self.memory_service.remember(
                statement,
                origin="explicit_remember",
                clear_tombstone=bool(args.get("clear_tombstone", False)),
            )
            if out.get("ok"):
                self.memory_service.render_to_file()
            return {
                "summary": out.get("message", ""),
                "sources": [{"type": "kb", "path": MEMORY_DOC_REL}],
                **out,
            }
        if action == "forget":
            out = self.memory_service.forget(
                fact_id=args.get("fact_id"), statement=statement
            )
            if out.get("ok"):
                self.memory_service.render_to_file()
            return {"summary": out.get("message", ""), "sources": [], **out}
        if action == "correct":
            out = self.memory_service.correct(
                fact_id=args.get("fact_id"),
                statement=statement,
                replacement=args.get("replacement", ""),
            )
            if out.get("ok"):
                self.memory_service.render_to_file()
            return {
                "summary": out.get("message", ""),
                "sources": [{"type": "kb", "path": MEMORY_DOC_REL}],
                **out,
            }
        return {
            "summary": f"未知 action: {action}",
            "sources": [],
            "ok": False,
            "error": "invalid_action",
        }

    def recall_memory(self, args: dict) -> dict:
        if not self.memory_service:
            return {"summary": "记忆服务未配置", "sources": [], "facts": [], "count": 0}
        out = self.memory_service.recall(
            args.get("query", ""),
            include_sources=bool(args.get("include_sources", False)),
            limit=int(args.get("limit", 10)),
        )
        return {
            "summary": f"找到 {out['count']} 条已确认记忆",
            "sources": [],
            **out,
        }
