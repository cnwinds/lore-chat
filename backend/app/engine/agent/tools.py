from __future__ import annotations

READ_ONLY_TOOLS = frozenset({"search_kb", "read_doc", "fetch_url", "web_search"})
WRITE_TOOLS = frozenset({"write_kb", "delete_kb", "ask_user"})


def can_parallelize(tool_names: list[str]) -> bool:
    return all(n in READ_ONLY_TOOLS for n in tool_names)


TOOL_LABELS = {
    "search_kb": "检索本地知识库",
    "read_doc": "读取文档",
    "fetch_url": "打开链接",
    "web_search": "搜索网页",
    "write_kb": "整理到知识库",
    "delete_kb": "删除知识库内容",
    "ask_user": "征询用户",
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
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_doc",
            "description": "读取知识库中指定路径的文档全文",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文档相对路径，如 技术/docker/常用命令.md"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "抓取并解析网页内容，转为 Markdown",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要抓取的 HTTP/HTTPS 链接"},
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


class ToolRegistry:
    def __init__(self, retriever, repo, organizer, fetcher, web_search, pending):
        self.retriever = retriever
        self.repo = repo
        self.organizer = organizer
        self.fetcher = fetcher
        self.web_search = web_search
        self.pending = pending

    async def execute(
        self, name: str, args: dict, *, active_doc_path: str | None = None
    ) -> dict:
        if name == "search_kb":
            return self._search_kb(args)
        if name == "read_doc":
            return self._read_doc(args)
        if name == "fetch_url":
            return await self._fetch_url(args)
        if name == "web_search":
            return await self._web_search(args)
        if name == "write_kb":
            return self._write_kb(args, active_doc_path=active_doc_path)
        if name == "delete_kb":
            return self._delete_kb(args)
        if name == "ask_user":
            return self._ask_user(args)
        return {"summary": f"未知工具：{name}", "sources": [], "error": f"unknown tool: {name}"}

    def _search_kb(self, args: dict) -> dict:
        query = args["query"]
        k = args.get("k", 5)
        hits = self.retriever.search(query, k=k)
        sources = [
            {"type": "kb", "path": h.source, "excerpt": h.chunk[:200]}
            for h in hits
        ]
        return {
            "summary": f"找到 {len(hits)} 条相关内容",
            "sources": sources,
            "hits": hits,
        }

    def _read_doc(self, args: dict) -> dict:
        path = args["path"]
        try:
            doc = self.repo.read_doc(path)
        except FileNotFoundError:
            return {
                "summary": f"文档不存在：{path}",
                "sources": [],
                "error": f"FileNotFoundError: {path}",
            }
        return {
            "summary": f"读取 {path}（{len(doc.body)} 字）",
            "sources": [{"type": "kb", "path": doc.rel_path}],
            "body": doc.body,
        }

    async def _fetch_url(self, args: dict) -> dict:
        url = args["url"]
        result = await self.fetcher.fetch(url)
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
        return {
            "summary": result.title or result.url,
            "sources": sources,
            "markdown": result.markdown,
        }

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
