from __future__ import annotations

import asyncio

from app.engine.conversation_context import read_conversation_context
from app.engine.kb_structure import summarize_kb_structure
from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.memory.constants import MEMORY_DOC_REL
from app.engine.conversations import ConversationStore
from app.engine.disclosure import disclose, disclosure_summary
from app.engine.patch import Edit, Insert, apply_edits, apply_insert
from app.storage.kb_paths import KbPathError
from app.engine.agent.tool_catalog import (
    TOOL_DEFINITIONS,
    TOOL_LABELS,
    WRITE_TOOLS,
    READ_ONLY_TOOLS,
    _DEFAULT_DISCLOSURE_CHARS,
    can_parallelize,
    resolve_kb_location,
    select_tools,
)

# 兼容旧 import 路径
__all__ = [
    "ToolRegistry",
    "TOOL_DEFINITIONS",
    "TOOL_LABELS",
    "select_tools",
    "can_parallelize",
    "READ_ONLY_TOOLS",
    "WRITE_TOOLS",
]

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
        memory_service=None,
        knowledge_writer: KnowledgeWriter | None = None,
    ):
        self.retriever = retriever
        self.repo = repo
        self.organizer = organizer
        self.fetcher = fetcher
        self.web_search = web_search
        self.pending = pending
        self.conversations = conversations
        self.system_layer = system_layer
        writer = knowledge_writer or getattr(organizer, "writer", None)
        if writer is None:
            if indexer is None:
                raise ValueError("ToolRegistry requires knowledge_writer or indexer")
            writer = KnowledgeWriter(repo, indexer)
        self.knowledge_writer = writer
        self.disclosure_chars = disclosure_chars
        self.edit_doc_max_edits = edit_doc_max_edits
        self.edit_doc_max_patch_chars = edit_doc_max_patch_chars
        self.edit_doc_require_read = edit_doc_require_read
        self.conversation_context_max_chars = conversation_context_max_chars
        self.memory_service = memory_service
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
            return await asyncio.to_thread(
                self._search_kb, args, conversation_id=conversation_id
            )
        if name == "read_doc":
            return await asyncio.to_thread(
                self._read_doc, args, conversation_id=conversation_id
            )
        if name == "list_kb_structure":
            return await asyncio.to_thread(self._list_kb_structure, args)
        if name == "read_conversation_context":
            return await asyncio.to_thread(self._read_conversation_context, args)
        if name == "fetch_url":
            return await self._fetch_url(args)
        if name == "web_search":
            return await self._web_search(args)
        if name == "write_kb":
            return await asyncio.to_thread(self._write_kb, args)
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
        if name == "move_doc":
            return await asyncio.to_thread(self._move_doc, args)
        if name == "ask_user":
            return self._ask_user(args)
        if name == "manage_memory":
            return await asyncio.to_thread(
                self._manage_memory, args, conversation_id=conversation_id
            )
        if name == "recall_memory":
            return await asyncio.to_thread(self._recall_memory, args)
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

    def _search_kb(self, args: dict, *, conversation_id: str | None = None) -> dict:
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
        # 会话来源（未归档/已归档会话消息均可命中）标为 conversation，便于前端跳转
        if isinstance(h.source, str) and h.source.startswith("conv:"):
            out: dict = {"type": "conversation", "cid": h.source[5:], "excerpt": h.chunk[:240]}
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

    def _list_kb_structure(self, args: dict) -> dict:
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
        rel_path, err = resolve_kb_location(args)
        if err:
            return err
        result = self.organizer.summarize_conversation(
            transcript,
            conv=conv,
            forced_rel_path=rel_path,
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

    def _write_kb(self, args: dict) -> dict:
        rel_path, err = resolve_kb_location(args)
        if err:
            return err
        text = args["text"]
        if args.get("context"):
            text = args["context"] + "\n\n" + text
        result = self.organizer.ingest_text(text, forced_rel_path=rel_path)
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

    def _move_doc(self, args: dict) -> dict:
        from_path = args.get("from_path", "").replace("\\", "/").lstrip("/")
        if not from_path:
            return {
                "summary": "缺少 from_path",
                "sources": [],
                "error": "MISSING_PATH",
                "status": "failed",
            }
        try:
            new_path = self.knowledge_writer.move_document(
                from_path,
                str(args.get("to_directory", "")),
                str(args.get("to_filename", "")),
            )
        except FileNotFoundError:
            return {
                "summary": f"源文档不存在：{from_path}",
                "sources": [],
                "error": "NOT_FOUND",
                "status": "failed",
            }
        except ValueError as e:
            return {
                "summary": str(e),
                "sources": [],
                "error": "PROTECTED_OR_EXISTS",
                "status": "failed",
            }
        except KbPathError as e:
            return {
                "summary": str(e),
                "sources": [],
                "error": "INVALID_PATH",
                "status": "failed",
            }
        return {
            "summary": f"已移动 {from_path} → {new_path}",
            "sources": [{"type": "kb", "path": new_path}],
            "status": "saved",
            "rel_path": new_path,
            "from_path": from_path,
        }

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

        self.knowledge_writer.drop_from_index(deleted)
        self.knowledge_writer.record_deletion(path, deleted)

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

        if path.replace("\\", "/") == MEMORY_DOC_REL and self.memory_service:
            out = self._finalize_memory_edit(path, doc, result)
            self._mark_read(conversation_id, path)
            return out

        reindex_mode = self.knowledge_writer.save_edit(
            path,
            doc.meta,
            old_body,
            result.body,
            affected_start=result.affected_start,
            affected_end=result.affected_end,
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

    def _finalize_memory_edit(self, path: str, doc, result) -> dict:
        sync = self.memory_service.import_manual_document(doc.meta, result.body)
        if not sync.get("ok"):
            return {
                "summary": sync.get("message", "记忆同步失败"),
                "sources": [{"type": "kb", "path": path}],
                "status": "failed",
                "error": sync.get("error"),
            }
        self.repo.write_doc(
            path, doc.meta, result.body, commit_msg=f"edit memory: {path}"
        )
        self.knowledge_writer.drop_from_index([path])
        return {
            "summary": f"已更新 {path} 并同步记忆库",
            "sources": [{"type": "kb", "path": path}],
            "status": "saved",
            "reindex_mode": "skipped_memory",
        }

    def _manage_memory(self, args: dict, *, conversation_id: str | None = None) -> dict:
        if not self.memory_service:
            return {"summary": "记忆服务未配置", "sources": [], "ok": False, "error": "not_configured"}
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
            out = self.memory_service.forget(fact_id=args.get("fact_id"), statement=statement)
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
        return {"summary": f"未知 action: {action}", "sources": [], "ok": False, "error": "invalid_action"}

    def _recall_memory(self, args: dict) -> dict:
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
