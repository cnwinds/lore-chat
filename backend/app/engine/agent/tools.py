from __future__ import annotations

import asyncio

from app.engine.conversation_context import read_conversation_context
from app.engine.conversations import ConversationStore
from app.engine.disclosure import disclose, disclosure_summary
from app.engine.patch import Edit, Insert, apply_edits, apply_insert

READ_ONLY_TOOLS = frozenset({"search_kb", "read_doc", "read_conversation_context", "fetch_url", "web_search"})
WRITE_TOOLS = frozenset({
    "write_kb", "delete_kb", "ask_user", "summarize_conversation", "edit_doc",
})

_DEFAULT_DISCLOSURE_CHARS = 3000


def can_parallelize(tool_names: list[str]) -> bool:
    return all(n in READ_ONLY_TOOLS for n in tool_names)


TOOL_LABELS = {
    "search_kb": "检索本地知识库",
    "read_doc": "读取文档",
    "read_conversation_context": "读取会话邻近消息",
    "fetch_url": "打开链接",
    "web_search": "搜索网页",
    "write_kb": "整理到知识库",
    "summarize_conversation": "归档整段会话",
    "delete_kb": "删除知识库内容",
    "ask_user": "征询用户",
    "edit_doc": "局部编辑文档",
}

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": "检索本地知识库，查找与用户问题相关的文档片段",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词或问题"},
                    "k": {"type": "integer", "description": "返回条数，默认 5", "default": 5},
                    "scope": {
                        "type": "string",
                        "enum": ["all", "knowledge", "conversations"],
                        "description": "检索范围：全部 / 仅知识库 / 仅会话",
                    },
                    "conversation_id": {
                        "type": "string",
                        "description": "限定在某个会话内检索（scope=conversations 时有效）",
                    },
                    "cursor": {
                        "type": "string",
                        "description": "分页游标，用于续取上一页未返回的结果",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_doc",
            "description": (
                "按渐进式披露读取知识库文档：默认返回前 3000 字，并附结构大纲（各标题及字符位置）。"
                "内容不足时，用 offset 跳到相关小节或翻页继续读取，不要盲目全量读取。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文档相对路径，如 技术/docker/常用命令.md"},
                    "offset": {"type": "integer", "description": "从第几个字符开始读取，默认 0；可用返回的 next_offset 或大纲中的 @位置", "default": 0},
                    "limit": {"type": "integer", "description": "本次最多读取字符数，默认 3000", "default": 3000},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_conversation_context",
            "description": "读取某条会话消息及其前后若干条邻近消息（用于核验检索命中、展开上下文）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "message_id": {"type": "string"},
                    "before_messages": {"type": "integer", "minimum": 0, "maximum": 10, "default": 2},
                    "after_messages": {"type": "integer", "minimum": 0, "maximum": 10, "default": 2},
                },
                "required": ["conversation_id", "message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": (
                "抓取并解析网页为 Markdown，按渐进式披露返回：默认前 3000 字。"
                "同一链接会缓存，需要更多时用 offset 继续，不会重复抓取。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要抓取的 HTTP/HTTPS 链接"},
                    "offset": {"type": "integer", "description": "从第几个字符开始，默认 0；用返回的 next_offset 继续", "default": 0},
                    "limit": {"type": "integer", "description": "本次最多返回字符数，默认 3000", "default": 3000},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索，获取网页摘要（需已配置搜索 API）",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "k": {"type": "integer", "description": "返回条数，默认 5", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_kb",
            "description": "将高价值内容整理写入本地知识库",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要写入的正文内容"},
                    "context": {
                        "type": "string",
                        "description": "可选上下文（如来源说明），会拼接到正文前",
                    },
                    "target_path": {
                        "type": "string",
                        "description": "可选，指定写入目标文档路径（用户正在编辑的文档）",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_doc",
            "description": (
                "对已有知识库文档做局部修改（替换或插入）。"
                "修改前必须先 read_doc 读取目标区域；old_string 必须从 read_doc 返回内容中精确复制。"
                "小范围修改优先于 write_kb。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文档相对路径，如 技术/docker/常用命令.md",
                    },
                    "edits": {
                        "type": "array",
                        "description": "按顺序应用的多处替换（同一文件原子提交）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "old_string": {
                                    "type": "string",
                                    "description": "要被替换的原文（精确匹配，含换行）",
                                },
                                "new_string": {
                                    "type": "string",
                                    "description": "替换后的内容；删除内容时传空字符串",
                                },
                                "replace_all": {
                                    "type": "boolean",
                                    "description": "为 true 时替换所有匹配项，默认 false",
                                    "default": False,
                                },
                            },
                            "required": ["old_string", "new_string"],
                        },
                        "minItems": 1,
                    },
                    "insert": {
                        "type": "object",
                        "description": "在指定位置插入内容（不删除原文）。与 edits 互斥。",
                        "properties": {
                            "after_heading": {
                                "type": "string",
                                "description": "在此 Markdown 标题行之后插入，如 '## 部署步骤'",
                            },
                            "at_offset": {
                                "type": "integer",
                                "description": "或在此字符偏移处插入（来自 read_doc 大纲 @位置）",
                            },
                            "content": {
                                "type": "string",
                                "description": "要插入的 Markdown 正文",
                            },
                        },
                        "required": ["content"],
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_conversation",
            "description": (
                "把当前整段会话通读后全局重构、去重、成文，归档为一篇知识库文档。"
                "用户要求「总结/归档本次会话/整理成文档/生成会话纪要」时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_path": {
                        "type": "string",
                        "description": "可选，指定归并到的已有文档相对路径；不填则自动决定新建或并入相关文档",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_kb",
            "description": "删除知识库中的文档或目录（含目录下所有文件）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的相对路径，如 projects/mini-app/version-todo.md 或 projects/mini-app/",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "向用户提出选择题，等待用户确认后再继续",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "向用户展示的问题"},
                    "options": {
                        "type": "array",
                        "description": "选项列表，每项含 id 和 label",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                            },
                            "required": ["id", "label"],
                        },
                    },
                    "multi_select": {
                        "type": "boolean",
                        "description": "是否允许多选，默认 false",
                        "default": False,
                    },
                    "context": {
                        "type": "string",
                        "description": "可选背景信息，帮助用户理解选项",
                    },
                },
                "required": ["question", "options"],
            },
        },
    },
]

_MODE_NO_WRITE = "no_write"


def select_tools(mode: str, web_enabled: bool) -> list[dict]:
    """按 mode 与 web_enabled 硬门过滤下发给模型的工具集。

    - web_enabled=False：移除 web_search（保留 fetch_url，贴链接=显式意图）。
    - mode=no_write：移除 write_kb（/api/ask；此前仅靠 prompt 约束，此处收紧为硬门）。
    - mode=force_write：保留 write_kb（/api/ingest 依赖 prompt 强制调用）。

    /api/chat 使用 mode=default。ingest/ask 为测试与脚本同步 API，见
    docs/superpowers/specs/2026-07-12-ingest-ask-api-design.md
    """
    excluded: set[str] = set()
    if not web_enabled:
        excluded.add("web_search")
    if mode == _MODE_NO_WRITE:
        excluded.add("write_kb")
    return [d for d in TOOL_DEFINITIONS if d["function"]["name"] not in excluded]


class ToolRegistry:
    def __init__(
        self,
        retriever,
        repo,
        organizer,
        fetcher,
        web_search,
        pending,
        conversations=None,
        system_layer=None,
        indexer=None,
        disclosure_chars: int = _DEFAULT_DISCLOSURE_CHARS,
        edit_doc_max_edits: int = 10,
        edit_doc_max_patch_chars: int = 8192,
        edit_doc_require_read: bool = True,
        conversation_context_max_chars: int = 12000,
    ):
        self.retriever = retriever
        self.repo = repo
        self.organizer = organizer
        self.fetcher = fetcher
        self.web_search = web_search
        self.pending = pending
        self.conversations = conversations
        self.system_layer = system_layer
        self.indexer = indexer or getattr(organizer, "indexer", None)
        self.disclosure_chars = disclosure_chars
        self.edit_doc_max_edits = edit_doc_max_edits
        self.edit_doc_max_patch_chars = edit_doc_max_patch_chars
        self.edit_doc_require_read = edit_doc_require_read
        self.conversation_context_max_chars = conversation_context_max_chars
        self._read_guard: dict[str, set[str]] = {}
        self._fetch_cache: dict[str, object] = {}

    async def execute(
        self,
        name: str,
        args: dict,
        *,
        active_doc_path: str | None = None,
        conversation_id: str | None = None,
    ) -> dict:
        # 含同步 LLM/嵌入的工具放到线程，避免堵死事件循环（聊天中无法打开文档）
        if name == "search_kb":
            return await asyncio.to_thread(self._search_kb, args)
        if name == "read_doc":
            return await asyncio.to_thread(
                self._read_doc, args, conversation_id=conversation_id
            )
        if name == "read_conversation_context":
            return await asyncio.to_thread(self._read_conversation_context, args)
        if name == "fetch_url":
            return await self._fetch_url(args)
        if name == "web_search":
            return await self._web_search(args)
        if name == "write_kb":
            return await asyncio.to_thread(
                self._write_kb, args, active_doc_path=active_doc_path
            )
        if name == "edit_doc":
            return await asyncio.to_thread(
                self._edit_doc, args, conversation_id=conversation_id
            )
        if name == "summarize_conversation":
            return self._summarize_conversation(
                args, conversation_id=conversation_id
            )
        if name == "delete_kb":
            return await asyncio.to_thread(self._delete_kb, args)
        if name == "ask_user":
            return self._ask_user(args)
        return {"summary": f"未知工具：{name}", "sources": [], "error": f"unknown tool: {name}"}

    def _mark_read(self, conversation_id: str | None, path: str) -> None:
        if not conversation_id:
            return
        self._read_guard.setdefault(conversation_id, set()).add(path)

    def _is_read(self, conversation_id: str | None, path: str) -> bool:
        if not self.edit_doc_require_read:
            return True
        if not conversation_id:
            return False
        return path in self._read_guard.get(conversation_id, set())

    def _edit_doc_error(self, code: str, message: str, **extra) -> dict:
        out = {
            "summary": message,
            "sources": [],
            "status": "failed",
            "error": code,
            **extra,
        }
        if code == "NOT_READ":
            out["suggestion"] = "请先调用 read_doc 读取该文档后再 edit_doc"
        return out

    def _search_kb(self, args: dict) -> dict:
        query = args["query"]
        k = args.get("k", 5)
        scope = args.get("scope", "all")
        conversation_id = args.get("conversation_id")
        cursor = args.get("cursor")
        page = self.retriever.search(
            query,
            k=k,
            scope=scope,
            conversation_id=conversation_id,
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
        return out

    @staticmethod
    def _hit_source(h) -> dict:
        # 会话来源（未归档/已归档会话消息均可命中）标为 conversation，便于前端跳转
        if isinstance(h.source, str) and h.source.startswith("conv:"):
            out: dict = {"type": "conversation", "cid": h.source[5:], "excerpt": h.chunk[:240]}
            if h.message_id is not None:
                out["message_id"] = h.message_id
                out["start_char"] = h.start_char
                out["end_char"] = h.end_char
                out["offset_version"] = h.offset_version or "unicode-codepoint-v1"
            return out
        return {"type": "kb", "path": h.source, "excerpt": h.chunk[:200]}

    def _read_doc(self, args: dict, *, conversation_id: str | None = None) -> dict:
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
        self._mark_read(conversation_id, path)
        return out

    def _read_conversation_context(self, args: dict) -> dict:
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

    async def _fetch_url(self, args: dict) -> dict:
        url = args["url"]
        result = self._fetch_cache.get(url)
        if result is None:
            result = await self.fetcher.fetch(url)
            if not result.error:
                self._fetch_cache[url] = result
        if result.error:
            return {
                "summary": f"{url} — {result.error}",
                "sources": [],
                "error": result.error,
            }
        sources = [
            {
                "type": "web",
                "url": result.url,
                "title": result.title,
                "snippet": result.snippet,
            }
        ]
        offset = args.get("offset", 0)
        limit = args.get("limit", self.disclosure_chars)
        info = disclose(result.markdown, offset=offset, limit=limit, with_outline=True)
        label = result.title or result.url
        out = {
            "summary": disclosure_summary(label, info),
            "sources": sources,
            "markdown": info["body"],
            "total_chars": info["total_chars"],
            "offset": info["offset"],
            "returned_chars": info["returned_chars"],
            "has_more": info["has_more"],
        }
        if "next_offset" in info:
            out["next_offset"] = info["next_offset"]
        if "outline" in info:
            out["outline"] = info["outline"]
        return out

    def _summarize_conversation(
        self, args: dict, *, conversation_id: str | None = None
    ) -> dict:
        if not conversation_id or self.conversations is None:
            return {
                "summary": "当前不在具名会话中，无法归档整段会话。",
                "sources": [],
                "error": "no conversation context",
            }
        try:
            conv = self.conversations.get(conversation_id)
        except KeyError:
            return {
                "summary": "会话不存在，无法归档。",
                "sources": [],
                "error": f"conversation not found: {conversation_id}",
            }
        transcript = ConversationStore.full_transcript(conv)
        system_rules = self.system_layer.compose() if self.system_layer else ""
        result = self.organizer.summarize_conversation(
            transcript,
            hint_path=args.get("target_path"),
            system_rules=system_rules,
            conversation_id=conversation_id,
        )
        sources = (
            [{"type": "kb", "path": result.rel_path}] if result.rel_path else []
        )
        if result.status == "saved" and result.rel_path:
            # 归档后仍保留原始消息的全文索引（会话消息级 FTS），
            # 便于历史检索；仅文档级摘要落库，不清空 conversation_chunks_v2。
            self.conversations.mark_summarized(conversation_id, result.rel_path)
        return {"summary": result.message, "sources": sources}

    async def _web_search(self, args: dict) -> dict:
        query = args["query"]
        k = args.get("k", 5)
        results, err = await self.web_search.search(query, k=k)
        if err:
            return {"summary": err, "sources": [], "error": err}
        provider = self.web_search.provider_name or "unknown"
        sources = [
            {
                "type": "search",
                "provider": provider,
                "url": r.url,
                "title": r.title,
                "snippet": r.snippet,
            }
            for r in results
        ]
        return {
            "summary": f"搜索到 {len(results)} 条结果",
            "sources": sources,
        }

    def _write_kb(self, args: dict, *, active_doc_path: str | None = None) -> dict:
        text = args["text"]
        if args.get("context"):
            text = args["context"] + "\n\n" + text
        hint_path = args.get("target_path") or active_doc_path
        result = self.organizer.ingest_text(text, hint_path=hint_path)
        sources = [{"type": "kb", "path": result.rel_path}] if result.rel_path else []
        out: dict = {
            "summary": result.message,
            "sources": sources,
            "ingest_result": result,
            "status": result.status,
            "rel_path": result.rel_path,
        }
        if result.question_id:
            out["question_id"] = result.question_id
        return out

    def _delete_kb(self, args: dict) -> dict:
        path = args["path"]
        try:
            deleted = self.repo.delete_path(path, commit_msg=f"delete: {path}")
        except FileNotFoundError:
            return {
                "summary": f"路径不存在：{path}",
                "sources": [],
                "error": f"FileNotFoundError: {path}",
            }
        except ValueError as e:
            return {"summary": str(e), "sources": [], "error": str(e)}

        for rel in deleted:
            if rel.endswith(".md"):
                self.organizer.indexer.remove_doc(rel)

        if deleted:
            self.repo.log_change(
                f"删除 {path}（共 {len(deleted)} 个文件）",
                commit_msg=f"chore: changelog for delete {path}",
            )

        return {
            "summary": f"已删除 {path}（{len(deleted)} 个文件）",
            "sources": [],
            "deleted_paths": deleted,
        }

    def _edit_doc(self, args: dict, *, conversation_id: str | None = None) -> dict:
        path = args["path"]
        edits_raw = args.get("edits")
        insert_raw = args.get("insert")

        if edits_raw and insert_raw:
            return self._edit_doc_error("INVALID", "edits 与 insert 不能同时使用")
        if not edits_raw and not insert_raw:
            return self._edit_doc_error("INVALID", "必须提供 edits 或 insert")

        if not self.repo.is_writable(path):
            return self._edit_doc_error("PROTECTED", f"路径不可写：{path}")

        if not self._is_read(conversation_id, path):
            return self._edit_doc_error("NOT_READ", f"请先 read_doc 再编辑：{path}")

        try:
            doc = self.repo.read_doc(path)
        except FileNotFoundError:
            return self._edit_doc_error("NOT_FOUND", f"文档不存在：{path}")

        old_body = doc.body

        if insert_raw:
            if not isinstance(insert_raw, dict):
                return self._edit_doc_error("INVALID", "insert 参数格式无效")
            insert = Insert(
                content=insert_raw.get("content", ""),
                after_heading=insert_raw.get("after_heading"),
                at_offset=insert_raw.get("at_offset"),
            )
            result = apply_insert(
                old_body, insert, max_patch_chars=self.edit_doc_max_patch_chars
            )
        else:
            if len(edits_raw) > self.edit_doc_max_edits:
                return self._edit_doc_error(
                    "TOO_LARGE",
                    f"单次最多 {self.edit_doc_max_edits} 处 edits",
                )
            edits = [
                Edit(
                    old_string=e["old_string"],
                    new_string=e["new_string"],
                    replace_all=bool(e.get("replace_all", False)),
                )
                for e in edits_raw
            ]
            result = apply_edits(
                old_body, edits, max_patch_chars=self.edit_doc_max_patch_chars
            )

        return self._finalize_edit_doc(
            path, doc, old_body, result, conversation_id=conversation_id
        )

    def _finalize_edit_doc(
        self,
        path: str,
        doc,
        old_body: str,
        result,
        *,
        conversation_id: str | None = None,
    ) -> dict:
        if not result.ok:
            err = result.error
            out = self._edit_doc_error(err.code, result.message)
            if err.hint:
                out["hint"] = err.hint
            if err.occurrences:
                out["occurrences"] = err.occurrences
            if err.suggestion:
                out["suggestion"] = err.suggestion
            return out

        self.repo.write_doc(
            path, doc.meta, result.body, commit_msg=f"edit: {path}"
        )
        reindex_mode = "full"
        if self.indexer is not None:
            reindex_mode = self.indexer.reindex_doc_after_edit(
                path,
                old_body,
                result.body,
                result.affected_start,
                result.affected_end,
            )
        self.repo.log_change(
            f"Agent 局部编辑 {path}", commit_msg=f"chore: changelog edit {path}"
        )
        self._mark_read(conversation_id, path)

        return {
            "summary": f"已在 {path} {result.message}",
            "sources": [{"type": "kb", "path": path}],
            "status": "saved",
            "applied": result.applied,
            "preview": result.preview,
            "reindex_mode": reindex_mode,
        }

    def _ask_user(self, args: dict) -> dict:
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
        }
