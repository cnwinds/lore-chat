from __future__ import annotations


class MemoryTools:
    def __init__(self, memory_service) -> None:
        self.memory_service = memory_service

    def manage_memory(self, args: dict, *, conversation_id: str | None = None) -> dict:
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
            # 规格 §3#15 / §7.2：显式记住也写会话级出处
            out = self.memory_service.remember(
                statement,
                origin="explicit_remember",
                conversation_id=conversation_id,
                clear_tombstone=bool(args.get("clear_tombstone", False)),
            )
            return {
                "summary": out.get("message", ""),
                "sources": [],
                **out,
            }
        if action == "forget":
            out = self.memory_service.forget(
                fact_id=args.get("fact_id"), statement=statement
            )
            return {"summary": out.get("message", ""), "sources": [], **out}
        if action == "correct":
            out = self.memory_service.correct(
                fact_id=args.get("fact_id"),
                statement=statement,
                replacement=args.get("replacement", ""),
            )
            return {
                "summary": out.get("message", ""),
                "sources": [],
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
