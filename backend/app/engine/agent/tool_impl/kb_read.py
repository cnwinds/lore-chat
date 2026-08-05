from __future__ import annotations

from app.engine.conversation_context import read_conversation_context
from app.engine.disclosure import disclose, disclosure_summary
from app.engine.kb_structure import summarize_kb_structure
from app.engine.agent.tool_impl.doc_read_guard import DocReadGuard
from app.storage.repo import KnowledgeRepo


class KbReadTools:
    def __init__(
        self,
        *,
        repo: KnowledgeRepo,
        retriever,
        read_guard: DocReadGuard,
        disclosure_chars: int,
        conversations=None,
        conversation_context_max_chars: int = 12000,
    ) -> None:
        self.repo = repo
        self.retriever = retriever
        self.read_guard = read_guard
        self.disclosure_chars = disclosure_chars
        self.conversations = conversations
        self.conversation_context_max_chars = conversation_context_max_chars

    def search_kb(self, args: dict, *, conversation_id: str | None = None) -> dict:
        query = args["query"]
        k = args.get("k", 5)
        scope = args.get("scope", "all")
        explicit_cid = args.get("conversation_id")
        exclude_cid = None if explicit_cid else conversation_id
        cursor = args.get("cursor")
        page = self.retriever.search(
            query,
            k=k,
            scope=scope,
            conversation_id=explicit_cid,
            exclude_conversation_id=exclude_cid,
            cursor=cursor,
        )
        hits = page.hits
        sources = [self._hit_source(h) for h in hits]
        if page.cursor_expired:
            summary = "检索游标已过期（索引已更新），请重新发起检索"
        else:
            summary = f"找到 {len(hits)} 条相关内容"
        out = {
            "summary": summary,
            "sources": sources,
            "hits": hits,
            "has_more": page.has_more,
            "index_revision": page.index_revision,
        }
        if page.next_cursor:
            out["next_cursor"] = page.next_cursor
        if page.cursor_expired:
            out["cursor_expired"] = True
        if page.provenance_groups:
            out["provenance_groups"] = page.provenance_groups
        return out

    @staticmethod
    def _hit_source(h) -> dict:
        if isinstance(h.source, str) and h.source.startswith("conv:"):
            out: dict = {
                "type": "conversation",
                "cid": h.source[5:],
                "excerpt": h.chunk[:240],
            }
            if h.message_id is not None:
                out["message_id"] = h.message_id
                out["start_char"] = h.start_char
                out["end_char"] = h.end_char
                out["offset_version"] = h.offset_version or "unicode-codepoint-v1"
            if h.role:
                out["role"] = h.role
            if h.ts:
                out["ts"] = h.ts
            if h.conversation_title:
                out["conversation_title"] = h.conversation_title
            return out
        return {"type": "kb", "path": h.source, "excerpt": h.chunk[:200]}

    def read_doc(self, args: dict, *, conversation_id: str | None = None) -> dict:
        path = args["path"]
        try:
            doc = self.repo.read_doc(path)
        except FileNotFoundError:
            return {
                "summary": f"文档不存在：{path}",
                "sources": [],
                "error": f"FileNotFoundError: {path}",
            }
        offset = args.get("offset", 0)
        limit = args.get("limit", self.disclosure_chars)
        info = disclose(doc.body, offset=offset, limit=limit, with_outline=True)
        out = {
            "summary": disclosure_summary(f"读取 {path}", info),
            "sources": [{"type": "kb", "path": doc.rel_path}],
            "body": info["body"],
            "total_chars": info["total_chars"],
            "offset": info["offset"],
            "returned_chars": info["returned_chars"],
            "has_more": info["has_more"],
        }
        if "next_offset" in info:
            out["next_offset"] = info["next_offset"]
        if "outline" in info:
            out["outline"] = info["outline"]
        self.read_guard.mark(conversation_id, path)
        return out

    def list_kb_structure(self, args: dict) -> dict:
        del args
        data = summarize_kb_structure(self.repo)
        return {
            "summary": data["summary"],
            "sources": [],
            "directories": data["directories"],
            "root_docs": data["root_docs"],
            "top_level_categories": data["top_level_categories"],
            "protected_paths": data["protected_paths"],
            "total_docs": data["total_docs"],
        }

    def read_conversation_context(self, args: dict) -> dict:
        if not self.conversations:
            return {
                "summary": "会话存储未配置",
                "messages": [],
                "anchor": {"message_id": args.get("message_id")},
                "truncated": False,
                "error": "not_configured",
            }
        try:
            return read_conversation_context(
                self.conversations,
                conversation_id=args["conversation_id"],
                message_id=args["message_id"],
                before_messages=args.get("before_messages", 2),
                after_messages=args.get("after_messages", 2),
                max_chars=self.conversation_context_max_chars,
            )
        except KeyError:
            return {
                "summary": "消息或会话不存在",
                "messages": [],
                "anchor": {"message_id": args.get("message_id")},
                "truncated": False,
                "error": "not_found",
            }
