"""统一 lore:// 读工具：search / read / list。"""

from __future__ import annotations

import mimetypes
from typing import Any

from app.engine.context_view.compile import compile_search, SearchPlan
from app.engine.context_view.errors import (
    AmbiguousSubject,
    ContextViewError,
    InvalidUri,
    NotFound,
    OutOfScope,
)
from app.engine.context_view.hits import pair_hit_and_source
from app.engine.context_view.kb_kind import classify
from app.engine.context_view.listing import list_entries
from app.engine.context_view.scope import ViewScope
from app.engine.context_view.uri import (
    ConversationUri,
    KbUri,
    LORE_ROOT,
    LoreRoot,
    LoreUri,
    MemoryUri,
    format_uri,
)
from app.engine.conversation_context import read_conversation_context
from app.engine.disclosure import disclose, disclosure_summary
from app.engine.memory.cards import parse_scope
from app.engine.agent.tool_impl.doc_read_guard import DocReadGuard
from app.engine.disclosure import DisclosureWindows
from app.index.extract import extract_text
from app.storage.kb_text_files import is_kb_text_file
from app.time import normalize_search_ts


def _error_result(exc: ContextViewError) -> dict:
    if isinstance(exc, OutOfScope):
        uri = exc.uri_str
        return {
            "summary": f"路径越界：{uri}",
            "sources": [],
            "error": "out_of_scope",
            "uri": uri,
        }
    if isinstance(exc, NotFound):
        uri = exc.uri or str(exc)
        return {
            "summary": str(exc),
            "sources": [],
            "error": "not_found",
            "uri": uri,
        }
    if isinstance(exc, AmbiguousSubject):
        uri = exc.uri or str(exc)
        return {
            "summary": str(exc),
            "sources": [],
            "error": "ambiguous",
            "uri": uri,
        }
    uri = getattr(exc, "uri", None) or str(exc)
    return {
        "summary": str(exc),
        "sources": [],
        "error": "invalid_uri",
        "uri": uri,
    }


class ContextViewTools:
    def __init__(
        self,
        *,
        repo,
        retriever,
        conversations,
        roles,
        read_guard: DocReadGuard,
        disclosure_windows: DisclosureWindows | None = None,
        conversation_context_max_chars: int = 12000,
        memory_service=None,
        cards=None,
        channel_instances=None,
    ) -> None:
        self.repo = repo
        self.retriever = retriever
        self.conversations = conversations
        self.roles = roles
        self.read_guard = read_guard
        self.disclosure = disclosure_windows or DisclosureWindows()
        self.conversation_context_max_chars = conversation_context_max_chars
        self.memory_service = memory_service
        self.cards = cards
        self.channel_instances = channel_instances

    def _scope(self, *, conversation_id: str | None) -> ViewScope | dict:
        if self.conversations is None or self.roles is None:
            return {
                "summary": "会话或角色存储未配置",
                "sources": [],
                "error": "not_configured",
            }
        if self.cards is None:
            return {
                "summary": "记忆卡片未配置",
                "sources": [],
                "error": "not_configured",
            }
        try:
            return ViewScope.build(
                conversations=self.conversations,
                roles=self.roles,
                cards=self.cards,
                channel_instances=self.channel_instances,
                conversation_id=conversation_id,
            )
        except KeyError:
            return {
                "summary": "未知会话",
                "sources": [],
                "error": "not_found",
                "uri": conversation_id or "",
            }

    def search(self, args: dict, *, conversation_id: str | None = None) -> dict:
        scope = self._scope(conversation_id=conversation_id)
        if isinstance(scope, dict):
            return scope
        query = args["query"]
        k = max(1, min(20, int(args.get("k", 5))))
        cursor = args.get("cursor")
        ts_after = normalize_search_ts(args.get("ts_after"))
        ts_before = normalize_search_ts(args.get("ts_before"))
        raw_paths = args.get("paths")
        if raw_paths is None:
            path_strs = scope.default_search_paths()
        else:
            path_strs = list(raw_paths)

        try:
            plan = compile_search(scope, path_strs)
        except ContextViewError as exc:
            return _error_result(exc)

        if cursor:
            page = self.retriever.search(
                query,
                k=k,
                cursor=cursor,
                cursor_binding=conversation_id or "",
            )
            return self._format_search_page(
                scope,
                page,
                query,
                paths=plan.paths,
                memory=None,
            )

        page = None
        if plan.search_kb or plan.search_conversations:
            if plan.search_kb and plan.search_conversations:
                rscope = "all"
            elif plan.search_kb:
                rscope = "knowledge"
            else:
                rscope = "conversations"
            page = self.retriever.search(
                query,
                k=k,
                scope=rscope,
                kb_prefixes=plan.kb_prefixes if plan.search_kb else None,
                conversation_ids=plan.conversation_ids
                if plan.search_conversations
                else None,
                role_id=None,
                conversation_id=None,
                exclude_conversation_id=None,
                ts_after=ts_after,
                ts_before=ts_before,
                cursor_binding=conversation_id or "",
            )
        else:
            from app.engine.retriever import SearchPage

            rev = (
                self.retriever.index_revision.get()
                if self.retriever.index_revision
                else 0
            )
            page = SearchPage(hits=[], has_more=False, next_cursor=None, index_revision=rev)

        memory_items = None
        if plan.memory_targets:
            memory_items = self._search_memory(query, plan)

        return self._format_search_page(
            scope,
            page,
            query,
            paths=plan.paths,
            memory=memory_items,
        )

    def _search_memory(self, query: str, plan: SearchPlan) -> list[dict]:
        buckets: list[list[dict]] = []
        for scope_key, kind_filter in plan.memory_targets:
            if scope_key == "owner":
                if not self.memory_service:
                    continue
                raw = self.memory_service.recall(
                    query, limit=10, kind=kind_filter
                )
                items = []
                for f in raw.get("facts") or []:
                    kind = f.get("category") or kind_filter or ""
                    uri = format_uri(
                        MemoryUri("owner", None, kind, f.get("fact_id"), False)
                    )
                    items.append(
                        {
                            "uri": uri,
                            "kind": kind,
                            "text": f.get("statement") or "",
                            "origin": f.get("origin") or "",
                            "fact_id": f.get("fact_id"),
                        }
                    )
                buckets.append(items)
            else:
                if not self.cards:
                    continue
                items = self._recall_cards(scope_key, query, kind_filter)
                buckets.append(items)

        out: list[dict] = []
        idx = 0
        while len(out) < 10:
            progressed = False
            for bucket in buckets:
                if idx < len(bucket):
                    out.append(bucket[idx])
                    progressed = True
                    if len(out) >= 10:
                        break
            if not progressed:
                break
            idx += 1
        return out[:10]

    def _recall_cards(
        self, scope_key: str, query: str, kind_filter: str | None
    ) -> list[dict]:
        if self.cards is None:
            return []
        lim = 10
        q = (query or "").strip()
        if q and self.cards.index is not None:
            facts = self.cards.index.search(scope_key, q, limit=lim, mode="recall")
        else:
            facts = self.cards.store(scope_key).search_confirmed(query, limit=lim)
        items: list[dict] = []
        scope_kind, subject = parse_scope(scope_key)
        for f in facts:
            kind = f.get("category") or ""
            if kind_filter and kind != kind_filter:
                continue
            stmt = f.get("statement") or ""
            uri = format_uri(
                MemoryUri(scope_kind, subject, kind, f["id"], False)
            )
            items.append(
                {
                    "uri": uri,
                    "kind": kind,
                    "text": stmt,
                    "origin": f.get("origin") or "",
                    "card_id": f["id"],
                }
            )
            if len(items) >= lim:
                break
        return items

    def _format_search_page(
        self,
        scope: ViewScope,
        page,
        query: str,
        *,
        paths: list[str],
        memory: list[dict] | None,
    ) -> dict:
        hits: list[dict] = []
        sources: list[dict] = []
        for h in page.hits:
            pair = pair_hit_and_source(scope, h)
            if pair is None:
                continue
            hit_dict, src_dict = pair
            hits.append(hit_dict)
            sources.append(src_dict)

        if page.cursor_expired:
            summary = "检索游标已过期（索引已更新），请重新发起检索"
        elif page.match_strength == "none":
            summary = "未找到足够相关的资料"
        elif page.match_strength == "weak":
            summary = "未找到足够相关的资料（仅有弱相关命中）"
        else:
            summary = f"找到 {len(hits)} 条相关内容"
        if memory:
            summary += f"；记忆 {len(memory)} 条"

        out: dict[str, Any] = {
            "summary": summary,
            "sources": sources,
            "hits": hits,
            "has_more": page.has_more,
            "index_revision": page.index_revision,
            "match_strength": page.match_strength,
            "paths": paths,
        }
        if memory is not None:
            out["memory"] = memory
        if page.next_cursor:
            out["next_cursor"] = page.next_cursor
        if page.cursor_expired:
            out["cursor_expired"] = True
        if page.provenance_groups:
            out["provenance_groups"] = page.provenance_groups
        return out

    def read(self, args: dict, *, conversation_id: str | None = None) -> dict:
        scope = self._scope(conversation_id=conversation_id)
        if isinstance(scope, dict):
            return scope
        uri_str = (args.get("uri") or "").strip()
        if not uri_str:
            return {
                "summary": "缺少 uri",
                "sources": [],
                "error": "invalid_uri",
                "uri": "",
            }
        try:
            parsed = scope.resolve_and_check(uri_str)
        except ContextViewError as exc:
            return _error_result(exc)

        if isinstance(parsed, KbUri):
            if parsed.is_dir or not parsed.rel_path:
                return {
                    "summary": "这是目录，请用 list 浏览",
                    "sources": [],
                    "error": "is_directory",
                    "uri": format_uri(parsed),
                }
            return self._read_kb(parsed, args, conversation_id=conversation_id)

        if isinstance(parsed, ConversationUri):
            return self._read_conversation(parsed, args, conversation_id=conversation_id)

        if isinstance(parsed, MemoryUri):
            return self._read_memory(
                scope, parsed, args, conversation_id=conversation_id
            )

        if isinstance(parsed, LoreRoot):
            return {
                "summary": "这是根目录，请用 list 浏览",
                "sources": [],
                "error": "is_directory",
                "uri": LORE_ROOT,
            }
        return {"summary": "不支持的 URI", "sources": [], "error": "invalid_uri"}

    def _read_kb(
        self, uri: KbUri, args: dict, *, conversation_id: str | None
    ) -> dict:
        path = uri.rel_path.replace("\\", "/").lstrip("/")
        if is_kb_text_file(path):
            return self._read_kb_text(path, args, conversation_id=conversation_id)
        if classify(path) == "binary":
            return self._read_kb_binary(path, uri, args)
        try:
            doc = self.repo.read_doc(path)
        except FileNotFoundError:
            return {
                "summary": f"文档不存在：{path}",
                "sources": [],
                "error": "not_found",
                "uri": format_uri(uri),
            }
        offset = args.get("offset", 0)
        limit = self.disclosure.resolve_args(args)
        info = disclose(
            doc.body,
            offset=offset,
            limit=limit,
            with_outline=True,
            max_chars=self.disclosure.max_chars,
        )
        rel = doc.rel_path
        out = {
            "summary": disclosure_summary(f"读取 {rel}", info),
            "sources": [
                {
                    "type": "kb",
                    "path": rel,
                    "uri": format_uri(KbUri(rel, False)),
                }
            ],
            "body": info["body"],
            "total_chars": info["total_chars"],
            "offset": info["offset"],
            "returned_chars": info["returned_chars"],
            "has_more": info["has_more"],
            "meta": dict(doc.meta),
            "uri": format_uri(uri),
            "kind": "doc",
        }
        if "next_offset" in info:
            out["next_offset"] = info["next_offset"]
        if "outline" in info:
            out["outline"] = info["outline"]
        self.read_guard.mark(conversation_id, rel)
        return out

    def _read_kb_text(
        self, path: str, args: dict, *, conversation_id: str | None
    ) -> dict:
        uri = format_uri(KbUri(path, False))
        try:
            data = self.repo.read_bytes(path)
        except FileNotFoundError:
            return {
                "summary": f"文件不存在：{path}",
                "sources": [],
                "error": "not_found",
                "uri": uri,
            }
        text = data.decode("utf-8", errors="replace")
        offset = args.get("offset", 0)
        limit = self.disclosure.resolve_args(args)
        info = disclose(
            text,
            offset=offset,
            limit=limit,
            with_outline=False,
            max_chars=self.disclosure.max_chars,
        )
        out = {
            "summary": disclosure_summary(f"读取 {path}", info),
            "sources": [{"type": "kb", "path": path, "uri": uri}],
            "body": info["body"],
            "total_chars": info["total_chars"],
            "offset": info["offset"],
            "returned_chars": info["returned_chars"],
            "has_more": info["has_more"],
            "uri": uri,
            "kind": "text",
        }
        if "next_offset" in info:
            out["next_offset"] = info["next_offset"]
        self.read_guard.mark(conversation_id, path)
        return out

    def _read_kb_binary(self, path: str, uri: KbUri, args: dict) -> dict:
        abs_p = self.repo.abs_path(path)
        try:
            size = abs_p.stat().st_size
        except FileNotFoundError:
            return {
                "summary": f"文件不存在：{path}",
                "sources": [],
                "error": "not_found",
                "uri": format_uri(uri),
            }
        except OSError:
            return {
                "summary": f"无法读取文件：{path}",
                "sources": [],
                "error": "not_found",
                "uri": format_uri(uri),
            }
        mime, _ = mimetypes.guess_type(path)
        out: dict[str, Any] = {
            "summary": f"二进制文件 {path}（{size} 字节）",
            "sources": [{"type": "kb", "path": path, "uri": format_uri(uri)}],
            "uri": format_uri(uri),
            "kind": "binary",
            "size": size,
            "mime": mime or "application/octet-stream",
        }
        extracted = extract_text(abs_p)
        if extracted.strip():
            offset = args.get("offset", 0)
            limit = self.disclosure.resolve_args(args)
            info = disclose(
                extracted,
                offset=offset,
                limit=limit,
                with_outline=False,
                max_chars=self.disclosure.max_chars,
            )
            out["body"] = info["body"]
            out["extracted"] = True
            out["total_chars"] = info["total_chars"]
            out["offset"] = info["offset"]
            out["returned_chars"] = info["returned_chars"]
            out["has_more"] = info["has_more"]
            if "next_offset" in info:
                out["next_offset"] = info["next_offset"]
        return out

    def _read_conversation(
        self,
        uri: ConversationUri,
        args: dict,
        *,
        conversation_id: str | None,
    ) -> dict:
        if not self.conversations:
            return {
                "summary": "会话存储未配置",
                "sources": [],
                "error": "not_configured",
            }
        cid = uri.conversation_id
        mid = uri.message_id
        if not cid:
            return {
                "summary": "缺少会话 id",
                "sources": [],
                "error": "invalid_uri",
                "uri": format_uri(uri),
            }
        before = args.get("before", 2)
        after = args.get("after", 2)
        try:
            result = read_conversation_context(
                self.conversations,
                conversation_id=cid,
                message_id=mid,
                before_messages=before,
                after_messages=after,
                max_chars=self.conversation_context_max_chars,
                current_conversation_id=conversation_id,
            )
        except KeyError:
            return {
                "summary": "消息或会话不存在",
                "sources": [],
                "error": "not_found",
                "uri": format_uri(uri),
            }
        if result.get("error") == "forbidden":
            return {
                "summary": result.get("summary") or "无权读取",
                "sources": [],
                "error": "out_of_scope",
                "uri": format_uri(uri),
            }
        scope = self._scope(conversation_id=conversation_id)
        if isinstance(scope, dict):
            return scope
        bucket, owner = scope.conversation_bucket(cid)
        for msg in result.get("messages") or []:
            muri = ConversationUri(
                bucket=bucket,  # type: ignore[arg-type]
                owner=owner,
                conversation_id=cid,
                message_id=msg.get("message_id"),
                is_dir=False,
            )
            msg["uri"] = format_uri(muri)
        tail_uri = ConversationUri(
            bucket=bucket,  # type: ignore[arg-type]
            owner=owner,
            conversation_id=cid,
            message_id=None,
            is_dir=True,
        )
        result["uri"] = format_uri(tail_uri if not mid else uri)
        return result

    def _read_memory(
        self,
        scope: ViewScope,
        uri: MemoryUri,
        args: dict,
        *,
        conversation_id: str | None,
    ) -> dict:
        if not uri.item_id or not uri.kind:
            return {
                "summary": "这是目录，请用 list 浏览",
                "sources": [],
                "error": "is_directory",
                "uri": format_uri(uri),
            }
        include_sources = bool(args.get("include_sources"))
        if scope.turn_kind == "channel":
            include_sources = False

        if uri.scope_kind == "owner":
            if not self.memory_service:
                return {
                    "summary": "主人记忆未配置",
                    "sources": [],
                    "error": "not_configured",
                }
            fact = self.memory_service.store.get_fact(uri.item_id)
            if (
                not fact
                or fact.get("status") != "confirmed"
                or fact.get("category") != uri.kind
            ):
                return {
                    "summary": "记忆不存在或未确认",
                    "sources": [],
                    "error": "not_found",
                    "uri": format_uri(uri),
                }
            out = {
                "summary": "已读取主人记忆",
                "sources": [],
                "uri": format_uri(uri),
                "kind": uri.kind,
                "statement": fact.get("statement") or "",
                "origin": fact.get("origin") or "",
                "status": fact.get("status"),
                "updated_at": fact.get("updated_at"),
            }
            if include_sources:
                out["sources"] = self.memory_service.explain_sources(
                    uri.item_id, sensitivity=fact.get("sensitivity", "normal")
                )
            return out

        if self.cards is None:
            return {
                "summary": "记忆卡片未配置",
                "sources": [],
                "error": "not_configured",
            }
        if uri.scope_kind == "role":
            scope_key = f"role:{uri.subject}"
        else:
            scope_key = f"persona:{uri.subject}"
        fact = self.cards.store(scope_key).get_fact(uri.item_id)
        if (
            not fact
            or fact.get("status") != "confirmed"
            or fact.get("category") != uri.kind
        ):
            return {
                "summary": "卡片不存在或未确认",
                "sources": [],
                "error": "not_found",
                "uri": format_uri(uri),
            }
        return {
            "summary": "已读取知识卡片",
            "sources": [],
            "uri": format_uri(uri),
            "kind": uri.kind,
            "statement": fact.get("statement") or "",
            "origin": fact.get("origin") or "",
            "status": fact.get("status"),
            "updated_at": fact.get("updated_at"),
        }

    def list(self, args: dict, *, conversation_id: str | None = None) -> dict:
        scope = self._scope(conversation_id=conversation_id)
        if isinstance(scope, dict):
            return scope
        uri_str = (args.get("uri") or "").strip() or LORE_ROOT
        depth = int(args.get("depth", 1))
        cursor = args.get("cursor")
        offset = 0
        if cursor is not None:
            try:
                offset = int(str(cursor).strip())
                if offset < 0:
                    raise ValueError
            except ValueError:
                return {
                    "summary": "无效的 list 游标",
                    "sources": [],
                    "error": "invalid_cursor",
                    "entries": [],
                }

        try:
            parsed = scope.resolve_and_check(uri_str)
        except ContextViewError as exc:
            return _error_result(exc)

        if isinstance(parsed, ConversationUri) and parsed.conversation_id:
            return {
                "summary": "会话条目请用 read 读取，不能 list",
                "sources": [],
                "error": "use_read",
                "uri": format_uri(parsed),
            }
        if isinstance(parsed, KbUri) and not parsed.is_dir:
            return {
                "summary": "这是文件，请用 read 读取",
                "sources": [],
                "error": "not_directory",
                "uri": format_uri(parsed),
            }
        if isinstance(parsed, MemoryUri) and parsed.item_id:
            return {
                "summary": "记忆条目请用 read 读取",
                "sources": [],
                "error": "use_read",
                "uri": format_uri(parsed),
            }

        entries, has_more, next_off = list_entries(
            scope,
            self.repo,
            parsed,
            depth=depth,
            offset=offset,
        )
        listed_uri = uri_str
        if listed_uri != LORE_ROOT and not listed_uri.endswith("/"):
            listed_uri = listed_uri + "/"
        out = {
            "summary": f"列出 {len(entries)} 项",
            "sources": [],
            "entries": entries,
            "uri": listed_uri,
        }
        if has_more:
            out["has_more"] = True
            out["next_cursor"] = str(next_off)
        return out
