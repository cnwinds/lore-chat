from __future__ import annotations

from app.engine.conversation.transcript import ConversationTranscript


class KbReadTools:
    def __init__(
        self,
        *,
        repo,
        retriever,
        read_guard,
        disclosure_windows=None,
        conversations=None,
        conversation_context_max_chars: int = 12000,
    ) -> None:
        del repo, retriever, read_guard, disclosure_windows, conversation_context_max_chars
        self.conversations = conversations

    def read_last_tool_results(
        self, args: dict, *, conversation_id: str | None = None
    ) -> dict:
        """上一轮工具与检索的原始结果，按需取回（不再每轮强行注入）。"""
        del args
        if not (self.conversations and conversation_id):
            return {
                "summary": "缺少会话上下文，无法定位上一轮工具结果",
                "results": [],
                "error": "not_configured",
            }
        try:
            conv = self.conversations.get(conversation_id)
        except KeyError:
            return {"summary": "会话不存在", "results": [], "error": "not_found"}
        blocks = ConversationTranscript.last_tool_blocks(conv)
        if not blocks:
            return {"summary": "上一轮没有工具调用或检索结果", "results": []}
        results: list[dict] = []
        total = 0
        truncated = False
        for block in blocks:
            content = str(block.get("content") or block.get("summary") or "").strip()
            if len(content) > 2400:
                content = content[:2400] + "…（截断）"
                truncated = True
            total += len(content)
            if total > 12000:
                truncated = True
                break
            results.append(
                {
                    "tool": block.get("tool") or "",
                    "label": block.get("label") or "",
                    "query": block.get("query") or "",
                    "content": content,
                }
            )
        return {
            "summary": f"上一轮共 {len(blocks)} 次工具调用"
            + ("（内容已截断）" if truncated else ""),
            "results": results,
            "truncated": truncated,
        }
