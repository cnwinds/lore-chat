from __future__ import annotations

from app.engine.channel_plugins.types import is_channel_origin
from app.engine.memory.cards import parse_scope


class MemoryTools:
    def __init__(self, memory_service) -> None:
        self.memory_service = memory_service
        self.cards = None
        self.conversations = None

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

    def recall_cards(self, args: dict, *, conversation_id: str | None = None) -> dict:
        if not self.cards:
            return {
                "summary": "知识卡服务未配置",
                "cards": [],
                "count": 0,
                "ok": False,
                "error": "not_configured",
            }
        if conversation_id and self.conversations is not None:
            origin = self.conversations.get_origin(conversation_id)
            if is_channel_origin(origin):
                return {
                    "summary": "通道会话不可查阅角色知识卡",
                    "cards": [],
                    "count": 0,
                    "ok": False,
                    "error": "channel_forbidden",
                }
        role_arg = (args.get("role") or "").strip()
        if role_arg:
            scope = self.cards.resolve_subject(role_arg)
        elif conversation_id and self.conversations is not None:
            rid = self.conversations.get_role_id(conversation_id)
            scope = self.cards.scope_for_role(rid)
        else:
            scope = None
        if not scope:
            return {
                "summary": "未找到该角色",
                "cards": [],
                "count": 0,
                "ok": False,
                "error": "not_found",
            }
        subject_name = self._subject_name(scope)
        cards = self.cards.recall(
            scope,
            query=str(args.get("query") or ""),
            limit=int(args.get("limit", 10)),
        )
        return {
            "summary": f"找到 {len(cards)} 条「{subject_name}」的知识卡",
            "cards": cards,
            "count": len(cards),
            "ok": True,
        }

    def _subject_name(self, scope: str) -> str:
        try:
            kind, subject_id = parse_scope(scope)
        except ValueError:
            return scope
        roles = self.cards.roles
        try:
            if kind == "role":
                return roles.get(subject_id).get("name") or subject_id
            return roles.get_persona(subject_id).get("name") or subject_id
        except KeyError:
            return subject_id
