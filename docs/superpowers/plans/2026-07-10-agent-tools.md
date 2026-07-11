# Lorechat Agent 工具能力实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 lorechat 从 remember/recall 双流水线升级为统一 Agent：支持工具调用（本地检索、网页搜索、URL 抓取、知识库写入），SSE 时间线流式输出（含时间戳），前端可折叠展示工具步骤与可点击来源。

**Architecture:** 在现有 Organizer/Retriever 之上新增 `engine/agent/`（Orchestrator + Tools）和 `engine/web/`（Fetcher + Search）。扩展 `LLMClient` 支持 tool calling；`POST /api/chat` 改为 SSE 事件流；前端 `Chat.tsx` 消费事件构建 timeline 结构并持久化到 `conversations.json`。

**Tech Stack:** Python 3.11+, FastAPI SSE (`StreamingResponse`), httpx (async), markitdown, openai SDK tool calling, pytest; React + TypeScript + Vite。

**设计文档:** [2026-07-10-agent-tools-design.md](../specs/2026-07-10-agent-tools-design.md)

---

## 关键契约（跨任务共享，命名必须一致）

```python
# app/engine/agent/events.py
@dataclass
class SourceRef:
    type: str          # "kb" | "web" | "search"
    # kb: path, excerpt?, line?
    # web/search: url, title, snippet; search 另有 provider

def now_ts() -> str:
    """ISO 8601 本地时间，如 2026-07-10T10:44:32+08:00"""
    return datetime.now().astimezone().isoformat(timespec="seconds")

# app/models/llm.py
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

@dataclass
class ChatWithToolsResult:
    content: str | None
    tool_calls: list[ToolCall]

class LLMClient(Protocol):
    def chat(self, messages: list[dict], *, big: bool = False, temperature: float = 0.2) -> str: ...
    def chat_with_tools(
        self, messages: list[dict], tools: list[dict], *,
        big: bool = True, temperature: float = 0.2,
    ) -> ChatWithToolsResult: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...

# app/engine/web/search.py
@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

# app/engine/web/fetcher.py
@dataclass
class FetchResult:
    url: str
    title: str
    markdown: str
    snippet: str   # 前 300 字摘要

# app/engine/agent/tools.py
READ_ONLY_TOOLS = frozenset({"search_kb", "read_doc", "fetch_url", "web_search"})
WRITE_TOOLS = frozenset({"write_kb", "ask_user"})

def can_parallelize(tool_names: list[str]) -> bool:
    return all(n in READ_ONLY_TOOLS for n in tool_names)
```

```typescript
// frontend/src/api.ts
export type SourceRef =
  | { type: "kb"; path: string; excerpt?: string; line?: number }
  | { type: "web"; url: string; title: string; snippet: string }
  | { type: "search"; provider: string; url: string; title: string; snippet: string };

export type TimelineBlock =
  | { type: "tool"; id: string; tool: string; label: string; ts: string;
      status: "running" | "done"; summary?: string; sources?: SourceRef[]; duration_ms?: number }
  | { type: "parallel"; batch_id: string; ts: string; children: TimelineBlock[]; duration_ms?: number }
  | { type: "text"; ts: string; content: string };

export type ChatMessage = {
  role: "user" | "assistant";
  ts?: string;
  text?: string;           // 旧格式兼容 / user 消息
  timeline?: TimelineBlock[];
  sources?: SourceRef[];
};
```

---



## 文件结构

```
backend/app/
  config.py                          # 修改：Agent + 搜索配置
  deps.py                            # 修改：注册 AgentOrchestrator
  models/llm.py                      # 修改：chat_with_tools
  engine/
    agent/
      __init__.py                    # 新建
      events.py                      # 新建：SSE 事件构造 + now_ts
      prompts.py                     # 新建：system prompt
      tools.py                       # 新建：工具注册与执行
      orchestrator.py                # 新建：Agent 主循环
    web/
      __init__.py                    # 新建
      fetcher.py                     # 新建：URL 抓取 + SSRF 防护
      search.py                      # 新建：多提供商搜索
    conversations.py                 # 修改：消息带 ts
  api/routes.py                      # 修改：/chat SSE，ingest/ask 转 Agent
backend/tests/
  test_fetcher.py                    # 新建
  test_web_search.py                 # 新建
  test_agent_tools.py                # 新建
  test_agent_orchestrator.py         # 新建
  test_api.py                        # 修改：SSE 测试
frontend/src/
  api.ts                             # 修改：chatStream + 类型
  App.tsx                            # 修改：来源点击 + highlight
  components/
    Chat.tsx                         # 修改：SSE 时间线
    DocViewer.tsx                    # 修改：highlightText
    TimelineBlock.tsx                # 新建
    SourceChip.tsx                   # 新建
    SearchSnippetModal.tsx           # 新建
  index.css                          # 修改：时间线样式
```

---



## Task 1: Agent 配置项

**Files:**

- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Test: 无（下轮用）

- [ ] **Step 1: 扩展 Settings**

在 `backend/app/config.py` 的 `Settings` 类末尾添加：

```python
    # Agent
    agent_max_tool_calls: int = 8
    agent_parallel_tools: bool = True
    agent_max_parallel: int = 4
    fetch_url_timeout: int = 15
    fetch_url_max_bytes: int = 102400

    # Web search（配哪个用哪个）
    tavily_api_key: str | None = None
    serper_api_key: str | None = None
    brave_search_api_key: str | None = None
    search_provider_order: str = "tavily,serper,brave"
```

- [ ] **Step 2: 更新 .env.example**

在 `backend/.env.example` 末尾追加：

```env
# Agent
AGENT_MAX_TOOL_CALLS=8
AGENT_PARALLEL_TOOLS=true
AGENT_MAX_PARALLEL=4
FETCH_URL_TIMEOUT=15
FETCH_URL_MAX_BYTES=102400

# Web search（配哪个用哪个）
TAVILY_API_KEY=
SERPER_API_KEY=
BRAVE_SEARCH_API_KEY=
SEARCH_PROVIDER_ORDER=tavily,serper,brave
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py backend/.env.example
git commit -m "feat: add agent and web search configuration"
```

---



## Task 2: LLM tool calling 扩展

**Files:**

- Modify: `backend/app/models/llm.py`
- Test: `backend/tests/test_llm_tools.py`（新建）

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_llm_tools.py`：

```python
import json
from app.models.llm import FakeLLMClient, ToolCall


def test_fake_llm_chat_with_tools_returns_tool_calls():
    tc = ToolCall(id="c1", name="search_kb", arguments={"query": "docker"})
    llm = FakeLLMClient(tool_responses=[
        {"content": None, "tool_calls": [tc]},
        {"content": "docker 用于容器管理", "tool_calls": []},
    ])
    r1 = llm.chat_with_tools([{"role": "user", "content": "docker?"}], tools=[])
    assert r1.content is None
    assert len(r1.tool_calls) == 1
    assert r1.tool_calls[0].name == "search_kb"

    r2 = llm.chat_with_tools([{"role": "user", "content": "continue"}], tools=[])
    assert r2.content == "docker 用于容器管理"
    assert r2.tool_calls == []
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_llm_tools.py -v
```

Expected: FAIL `AttributeError: 'FakeLLMClient' object has no attribute 'chat_with_tools'`

- [ ] **Step 3: 实现**

在 `backend/app/models/llm.py` 添加：

```python
from dataclasses import dataclass, field

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

@dataclass
class ChatWithToolsResult:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
```

扩展 `LLMClient` Protocol 和 `OpenAILLMClient`：

```python
def chat_with_tools(
    self, messages: list[dict], tools: list[dict], *,
    big: bool = True, temperature: float = 0.2,
) -> ChatWithToolsResult:
    client = self._big if big else self._small
    model = self.settings.big_model if big else self.settings.small_model
    kwargs: dict = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        kwargs["tools"] = tools
    resp = client.chat.completions.create(**kwargs)
    msg = resp.choices[0].message
    tool_calls = []
    if msg.tool_calls:
        for tc in msg.tool_calls:
            tool_calls.append(ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=json.loads(tc.function.arguments or "{}"),
            ))
    return ChatWithToolsResult(content=msg.content, tool_calls=tool_calls)
```

扩展 `FakeLLMClient`：

```python
def __init__(self, chat_responses=None, tool_responses=None, embed_dim=16):
    self.chat_responses = list(chat_responses or [])
    self.tool_responses = list(tool_responses or [])
    ...

def chat_with_tools(self, messages, tools, *, big=True, temperature=0.2):
    self.calls.append({"messages": messages, "tools": tools, "big": big, "mode": "tools"})
    if self._i < len(self.tool_responses):
        raw = self.tool_responses[self._i]
        self._i += 1
        tcs = [ToolCall(**tc) for tc in raw.get("tool_calls", [])]
        return ChatWithToolsResult(content=raw.get("content"), tool_calls=tcs)
    return ChatWithToolsResult(content="", tool_calls=[])
```

- [ ] **Step 4: 运行测试通过**

```bash
cd backend && python -m pytest tests/test_llm_tools.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/llm.py backend/tests/test_llm_tools.py
git commit -m "feat: extend LLMClient with tool calling support"
```

---



## Task 3: WebFetcher（URL 抓取 + SSRF 防护）

**Files:**

- Create: `backend/app/engine/web/__init__.py`
- Create: `backend/app/engine/web/fetcher.py`
- Create: `backend/tests/test_fetcher.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_fetcher.py
import pytest
from unittest.mock import AsyncMock, patch
from app.engine.web.fetcher import WebFetcher, is_safe_url


def test_is_safe_url_rejects_localhost():
    assert is_safe_url("http://localhost/secret") is False
    assert is_safe_url("http://127.0.0.1/") is False


@pytest.mark.asyncio
async def test_fetch_rejects_unsafe_url():
    f = WebFetcher(timeout=5, max_bytes=10000)
    result = await f.fetch("http://127.0.0.1/admin")
    assert result.error is not None
    assert "拒绝" in result.error or "unsafe" in result.error.lower()


@pytest.mark.asyncio
async def test_fetch_returns_markdown():
    html = b"<html><head><title>Test</title></head><body><p>Hello world</p></body></html>"
    f = WebFetcher(timeout=5, max_bytes=10000)
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.content = html
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp
        result = await f.fetch("https://example.com/page")
    assert result.error is None
    assert result.title == "Test"
    assert "Hello world" in result.markdown
```

注意：`FetchResult` 需含 `error: str | None` 字段供错误路径使用。

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_fetcher.py -v
```

- [ ] **Step 3: 实现 fetcher.py**

```python
# backend/app/engine/web/fetcher.py
from __future__ import annotations
import ipaddress, socket
from dataclasses import dataclass
from urllib.parse import urlparse
import httpx
from markitdown import MarkItDown

@dataclass
class FetchResult:
    url: str
    title: str = ""
    markdown: str = ""
    snippet: str = ""
    error: str | None = None

def is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host or host in ("localhost",):
        return False
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
    except socket.gaierror:
        return False
    return True

class WebFetcher:
    def __init__(self, timeout: int = 15, max_bytes: int = 102400):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self._md = MarkItDown()

    async def fetch(self, url: str) -> FetchResult:
        if not is_safe_url(url):
            return FetchResult(url=url, error="拒绝访问私有或本地地址")
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True,
                headers={"User-Agent": "LorechatBot/1.0"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.content[: self.max_bytes]
            # 写临时文件给 markitdown（或直接用 bytes 转）
            import tempfile, os
            suffix = ".html" if b"<html" in content[:200].lower() else ".txt"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                md_result = self._md.convert(tmp_path)
                markdown = md_result.text_content or ""
            finally:
                os.unlink(tmp_path)
            title = _extract_title(content) or url
            snippet = markdown[:300].strip()
            return FetchResult(url=url, title=title, markdown=markdown, snippet=snippet)
        except Exception as e:
            return FetchResult(url=url, error=f"抓取失败: {e}")

def _extract_title(content: bytes) -> str:
    import re
    m = re.search(rb"<title[^>]*>([^<]+)</title>", content, re.I)
    return m.group(1).decode("utf-8", errors="replace").strip() if m else ""
```

在 `requirements.txt` 确认已有 `httpx` 和 `markitdown`（已有）。

- [ ] **Step 4: 测试通过**

```bash
cd backend && python -m pytest tests/test_fetcher.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/web/ backend/tests/test_fetcher.py
git commit -m "feat: add WebFetcher with SSRF protection"
```

---



## Task 4: WebSearch 多提供商

**Files:**

- Create: `backend/app/engine/web/search.py`
- Create: `backend/tests/test_web_search.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_web_search.py
import pytest
from unittest.mock import AsyncMock, patch
from app.config import Settings
from app.engine.web.search import WebSearch, TavilyProvider


@pytest.mark.asyncio
async def test_tavily_provider_parses_results():
    provider = TavilyProvider("test-key")
    mock_data = {"results": [{"title": "A", "url": "https://a.com", "content": "snippet a"}]}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.json.return_value = mock_data
        mock_resp.raise_for_status = lambda: None
        mock_post.return_value = mock_resp
        results = await provider.search("test", k=3)
    assert len(results) == 1
    assert results[0].title == "A"
    assert results[0].snippet == "snippet a"


def test_web_search_picks_first_configured_provider():
    settings = Settings(tavily_api_key=None, serper_api_key="sk-test", brave_search_api_key=None)
    ws = WebSearch(settings)
    assert ws.provider_name == "serper"


def test_web_search_no_provider_raises_clear_error():
    settings = Settings(tavily_api_key=None, serper_api_key=None, brave_search_api_key=None)
    ws = WebSearch(settings)
    assert ws.provider is None
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_web_search.py -v
```

- [ ] **Step 3: 实现 search.py**

核心结构：

```python
@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

class WebSearchProvider(Protocol):
    async def search(self, query: str, k: int = 5) -> list[SearchResult]: ...

class TavilyProvider:
  # POST https://api.tavily.com/search  body: {api_key, query, max_results}

class SerperProvider:
  # POST https://google.serper.dev/search  header: X-API-KEY

class BraveSearchProvider:
  # GET https://api.search.brave.com/res/v1/web/search  header: X-Subscription-Token

class WebSearch:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._provider, self.provider_name = self._resolve_provider()

    def _resolve_provider(self):
        order = [p.strip() for p in self.settings.search_provider_order.split(",")]
        mapping = {
            "tavily": (self.settings.tavily_api_key, TavilyProvider),
            "serper": (self.settings.serper_api_key, SerperProvider),
            "brave": (self.settings.brave_search_api_key, BraveSearchProvider),
        }
        for name in order:
            key, cls = mapping.get(name, (None, None))
            if key and cls:
                return cls(key), name
        return None, None

    async def search(self, query: str, k: int = 5) -> tuple[list[SearchResult], str | None]:
        if self._provider is None:
            return [], "未配置搜索 API，请在 backend/.env 中设置 TAVILY_API_KEY 等"
        results = await self._provider.search(query, k=k)
        return results, None
```

- [ ] **Step 4: 测试通过并 commit**

```bash
cd backend && python -m pytest tests/test_web_search.py -v
git add backend/app/engine/web/search.py backend/tests/test_web_search.py
git commit -m "feat: add multi-provider WebSearch"
```

---



## Task 5: SSE 事件辅助模块

**Files:**

- Create: `backend/app/engine/agent/__init__.py`
- Create: `backend/app/engine/agent/events.py`
- Create: `backend/tests/test_agent_events.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_agent_events.py
import json
from app.engine.agent.events import (
    now_ts, sse_event, tool_start, tool_result, text_delta, done,
)

def test_sse_event_format():
    ev = tool_start("t1", "search_kb", "检索本地知识库", {"query": "x"})
    assert ev.startswith("event: tool_start\n")
    data = json.loads(ev.split("data: ", 1)[1].strip())
    assert data["id"] == "t1"
    assert "ts" in data

def test_now_ts_has_timezone():
    ts = now_ts()
    assert "T" in ts
```

- [ ] **Step 2: 实现 events.py**

```python
# backend/app/engine/agent/events.py
from __future__ import annotations
import json
from datetime import datetime

def now_ts() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")

def sse_event(event_type: str, data: dict) -> str:
    if "ts" not in data:
        data = {**data, "ts": now_ts()}
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

def tool_start(id, tool, label, input_data):
    return sse_event("tool_start", {"id": id, "tool": tool, "label": label, "input": input_data})

def tool_result(id, tool, summary, sources=None, duration_ms=None, ts=None):
    payload = {"id": id, "tool": tool, "summary": summary, "sources": sources or []}
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if ts:
        payload["ts"] = ts
    return sse_event("tool_result", payload)

def parallel_batch_start(batch_id, tools):
    return sse_event("parallel_batch_start", {"batch_id": batch_id, "tools": tools})

def parallel_batch_end(batch_id, duration_ms):
    return sse_event("parallel_batch_end", {"batch_id": batch_id, "duration_ms": duration_ms})

def text_delta(delta):
    return sse_event("text_delta", {"delta": delta})

def done(sources, total_duration_ms):
    return sse_event("done", {"sources": sources, "total_duration_ms": total_duration_ms})

def error_event(message):
    return sse_event("error", {"message": message})
```

- [ ] **Step 3: 测试通过并 commit**

---



## Task 6: Agent 工具注册与执行

**Files:**

- Create: `backend/app/engine/agent/prompts.py`
- Create: `backend/app/engine/agent/tools.py`
- Create: `backend/tests/test_agent_tools.py`

- [ ] **Step 1: 写 prompts.py**

将设计文档 §3 决策原则写入 `SYSTEM_PROMPT` 常量；提供 `build_system_prompt(mode: str)` 支持：

- `"default"` — 正常 Agent
- `"force_write"` — ingest 端点用，强制 write_kb
- `"no_write"` — ask 端点用，禁止 write_kb

- [ ] **Step 2: 写失败测试**

```python
# backend/tests/test_agent_tools.py
import pytest
from app.engine.agent.tools import ToolRegistry, can_parallelize, READ_ONLY_TOOLS

def test_can_parallelize_read_only():
    assert can_parallelize(["search_kb", "fetch_url"]) is True
    assert can_parallelize(["search_kb", "write_kb"]) is False

@pytest.mark.asyncio
async def test_search_kb_tool(client_deps):  # 用 fixture 注入 retriever
    ...
```

- [ ] **Step 3: 实现 tools.py**

```python
TOOL_DEFINITIONS = [
    {"type": "function", "function": {
        "name": "search_kb",
        "description": "检索本地知识库",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}, "k": {"type": "integer", "default": 5}
        }, "required": ["query"]},
    }},
    # read_doc, fetch_url, web_search, write_kb, ask_user 同理
]

class ToolRegistry:
    def __init__(self, retriever, repo, organizer, fetcher, web_search, pending):
        ...

    async def execute(self, name: str, args: dict) -> dict:
        """返回 {summary, sources, error?} 供 orchestrator 组装事件"""
        if name == "search_kb":
            hits = self.retriever.search(args["query"], k=args.get("k", 5))
            sources = [{"type": "kb", "path": h.source, "excerpt": h.chunk[:200]} for h in hits]
            return {"summary": f"找到 {len(hits)} 条相关内容", "sources": sources, "hits": hits}
        elif name == "read_doc":
            doc = self.repo.read_doc(args["path"])
            return {"summary": f"读取 {args['path']}（{len(doc.body)} 字）", "body": doc.body, ...}
        elif name == "fetch_url":
            result = await self.fetcher.fetch(args["url"])
            if result.error:
                return {"summary": result.error, "sources": [], "error": result.error}
            sources = [{"type": "web", "url": result.url, "title": result.title, "snippet": result.snippet}]
            return {"summary": f"{result.title}", "sources": sources, "markdown": result.markdown}
        elif name == "web_search":
            results, err = await self.web_search.search(args["query"], k=args.get("k", 5))
            if err:
                return {"summary": err, "sources": [], "error": err}
            sources = [{"type": "search", "provider": self.web_search.provider_name, ...} for r in results]
            return {"summary": f"搜索到 {len(results)} 条结果", "sources": sources}
        elif name == "write_kb":
            text = args["text"]
            if args.get("context"):
                text = args["context"] + "\n\n" + text
            result = self.organizer.ingest_text(text)
            sources = [{"type": "kb", "path": result.rel_path}] if result.rel_path else []
            return {"summary": result.message, "sources": sources, "ingest_result": result}
        elif name == "ask_user":
            qid = self.pending.create(args["question"], args["options"])
            return {"summary": "等待用户选择", "question_id": qid, ...}
```

- [ ] **Step 4: 测试通过并 commit**

---



## Task 7: AgentOrchestrator 主循环

**Files:**

- Create: `backend/app/engine/agent/orchestrator.py`
- Create: `backend/tests/test_agent_orchestrator.py`
- Modify: `backend/app/deps.py`

- [ ] **Step 1: 写失败测试**

用 `FakeLLMClient` 脚本化两轮 tool calling：

```python
@pytest.mark.asyncio
async def test_orchestrator_emits_timeline_events():
  llm = FakeLLMClient(tool_responses=[
      {"content": None, "tool_calls": [ToolCall(id="1", name="search_kb", arguments={"query": "x"})]},
      {"content": "答案是 Y", "tool_calls": []},
  ])
  events = []
  async for ev in orchestrator.run("问题", mode="no_write"):
      events.append(ev)
  types = [e.split("\n")[0].replace("event: ", "") for e in events if e.startswith("event:")]
  assert "tool_start" in types
  assert "tool_result" in types
  assert "text_delta" in types
  assert "done" in types
```

- [ ] **Step 2: 实现 orchestrator.py**

核心逻辑：

```python
class AgentOrchestrator:
    async def run(self, user_text: str, *, mode: str = "default") -> AsyncIterator[str]:
        start = time.monotonic()
        messages = [
            {"role": "system", "content": build_system_prompt(mode)},
            {"role": "user", "content": user_text},
        ]
        all_sources = []
        tool_call_count = 0

        while tool_call_count < self.settings.agent_max_tool_calls:
            result = self.llm.chat_with_tools(messages, TOOL_DEFINITIONS, big=True)
            if result.tool_calls:
                # 分并行/串行批
                batches = self._split_batches(result.tool_calls)
                for batch in batches:
                    if len(batch) > 1 and self.settings.agent_parallel_tools and can_parallelize([tc.name for tc in batch]):
                        batch_id = uuid.uuid4().hex[:8]
                        yield parallel_batch_start(batch_id, [tc.name for tc in batch])
                        # asyncio.gather execute, yield tool_start/result per completion
                        yield parallel_batch_end(batch_id, duration)
                    else:
                        for tc in batch:
                            yield tool_start(tc.id, tc.name, LABELS[tc.name], tc.arguments)
                            t0 = time.monotonic()
                            out = await self.tools.execute(tc.name, tc.arguments)
                            yield tool_result(tc.id, tc.name, out["summary"], out.get("sources"), ...)
                            all_sources.extend(out.get("sources", []))
                            messages.append({"role": "assistant", "content": None, "tool_calls": [...]})
                            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(out)})
                    tool_call_count += len(batch)
                continue
            # 无 tool_calls → 输出正文
            if result.content:
                for chunk in self._chunk_text(result.content):  # 或直接整段
                    yield text_delta(chunk)
            break
        else:
            yield text_delta("（已达工具调用上限，以上为目前能给出的结论。）")

        yield done(all_sources, int((time.monotonic() - start) * 1000))
```

- [ ] **Step 3: 在 deps.py 注册**

```python
from app.engine.agent.orchestrator import AgentOrchestrator
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import WebSearch

@dataclass
class Container:
    ...
    agent: AgentOrchestrator

def build_container(...):
    fetcher = WebFetcher(settings.fetch_url_timeout, settings.fetch_url_max_bytes)
    web_search = WebSearch(settings)
    tools = ToolRegistry(retriever, repo, organizer, fetcher, web_search, pending)
    agent = AgentOrchestrator(settings, llm, tools)
```

- [ ] **Step 4: 测试通过并 commit**

---



## Task 8: API `/chat` 改 SSE

**Files:**

- Modify: `backend/app/api/routes.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: 写失败测试**

```python
def test_chat_returns_sse_stream(client):
    r = client.post("/api/chat", json={"text": "docker 怎么用"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    body = r.text
    assert "event: done" in body
    assert '"ts"' in body
```

- [ ] **Step 2: 修改 routes.py**

```python
from fastapi.responses import StreamingResponse

@router.post("/chat")
async def chat(body: ChatBody, request: Request):
    c = _c(request)

    async def event_generator():
        timeline_blocks = []
        assistant_ts = now_ts()
        text_buf = ""
        all_sources = []
        try:
            async for ev in c.agent.run(body.text, mode="default"):
                yield ev
                # 解析事件累积 timeline（用于持久化）
                ...
            assistant_msg = {"role": "assistant", "ts": assistant_ts, "timeline": timeline_blocks, "sources": all_sources}
            if body.conversation_id:
                c.conversations.append_exchange(body.conversation_id, body.text, assistant_msg, user_ts=now_ts())
        except Exception as e:
            yield error_event(str(e))

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

- [ ] **Step 3: 更新 ingest/ask 端点**

```python
@router.post("/ingest")
async def ingest(body: IngestBody, request: Request):
    # 消费 agent.run(mode="force_write") 全部事件，返回最终 write_kb 结果 JSON（兼容旧客户端）

@router.post("/ask")
async def ask(body: AskBody, request: Request):
    # 消费 agent.run(mode="no_write")，返回最终 text + sources JSON
```

- [ ] **Step 4: 测试通过并 commit**

---



## Task 9: 对话持久化升级

**Files:**

- Modify: `backend/app/engine/conversations.py`
- Modify: `backend/tests/test_conversations.py`

- [ ] **Step 1: 写失败测试**

```python
def test_append_exchange_stores_timeline_and_ts(tmp_path):
    store = ConversationStore(tmp_path / "c.json")
    cid = store.create()
    assistant = {
        "role": "assistant",
        "ts": "2026-07-10T10:00:00+08:00",
        "timeline": [{"type": "text", "ts": "...", "content": "hi"}],
        "sources": [],
    }
    store.append_exchange(cid, "hello", assistant, user_ts="2026-07-10T09:59:00+08:00")
    conv = store.get(cid)
    assert conv["messages"][0]["ts"] == "2026-07-10T09:59:00+08:00"
    assert conv["messages"][1]["timeline"][0]["type"] == "text"
```

- [ ] **Step 2: 修改 append_exchange**

```python
def append_exchange(self, cid, user_text, assistant_msg, user_ts=None):
    user_msg = {"role": "user", "text": user_text, "ts": user_ts or _now()}
    ...
```

- [ ] **Step 3: 测试通过并 commit**

---



## Task 10: 前端 `chatStream` API

**Files:**

- Modify: `frontend/src/api.ts`

- [ ] **Step 1: 添加类型和 chatStream 函数**

```typescript
export type ChatStreamEvent = {
  event: string;
  data: Record<string, unknown>;
};

export async function* chatStream(
  text: string,
  conversationId?: string | null,
): AsyncGenerator<ChatStreamEvent> {
  const r = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ text, conversation_id: conversationId ?? undefined }),
  });
  if (!r.ok) throw new Error(await r.text());
  const reader = r.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const lines = part.split("\n");
      const eventLine = lines.find((l) => l.startsWith("event: "));
      const dataLine = lines.find((l) => l.startsWith("data: "));
      if (eventLine && dataLine) {
        yield {
          event: eventLine.slice(7),
          data: JSON.parse(dataLine.slice(6)),
        };
      }
    }
  }
}
```

- [ ] **Step 2: Commit**

---



## Task 11: 前端时间线组件

**Files:**

- Create: `frontend/src/components/TimelineBlock.tsx`
- Create: `frontend/src/components/SourceChip.tsx`
- Create: `frontend/src/components/SearchSnippetModal.tsx`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: 实现 SourceChip**

点击行为：

- `kb` → `onOpenDoc(path, excerpt)`
- `web` → `window.open(url)`
- `search` → `onShowSnippet(source)`

- [ ] **Step 2: 实现 TimelineBlock**

- `tool` 块：折叠面板，显示 `label`、格式化的 `ts`（`HH:mm`）、`summary`、`duration_ms`
- `parallel` 块：标题「检索资料」，子项递归渲染
- `text` 块：`MarkdownContent` 渲染 `content`

- [ ] **Step 3: 实现 SearchSnippetModal**

弹层显示 `title`、`snippet`、「打开原文」链接。

- [ ] **Step 4: 添加 CSS**

`.timeline-tool`、`.timeline-parallel`、`.source-chip`、`.timeline-ts` 等。

- [ ] **Step 5: Commit**

---



## Task 12: Chat.tsx 接入 SSE 时间线

**Files:**

- Modify: `frontend/src/components/Chat.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 改造 send() 函数**

```typescript
async function send() {
  ...
  const assistantMsg: ChatMessage = {
    role: "assistant",
    ts: new Date().toISOString(),
    timeline: [],
    sources: [],
  };
  setMsgs((m) => [...m, assistantMsg]);
  const idx = msgs.length + 1; // 追踪位置

  for await (const { event, data } of chatStream(text, cid)) {
    setMsgs((prev) => {
      const copy = [...prev];
      const msg = { ...copy[idx] };
      msg.timeline = updateTimeline(msg.timeline ?? [], event, data);
      if (event === "done") msg.sources = data.sources as SourceRef[];
      copy[idx] = msg;
      return copy;
    });
    if (event === "tool_result" && data.tool === "write_kb") onSidebarRefresh?.();
  }
}
```

实现 `updateTimeline()` 处理 `tool_start`、`tool_result`、`parallel_batch_*`、`text_delta`。

- [ ] **Step 2: 旧消息兼容**

渲染时：若 `m.timeline` 存在用 `TimelineBlock`；否则将 `m.text` 包装为 `{type:"text", content:m.text}`。

- [ ] **Step 3: App.tsx 传入回调**

```typescript
<Chat
  onOpenSource={(src) => {
    if (src.type === "kb") { setHighlight(src.excerpt); openFile(src.path); }
  }}
  ...
/>
```

- [ ] **Step 4: 手动测试**

```powershell
.\lorechat.bat dev
```

发送「docker 怎么用」确认时间线渲染；发送带 GitHub 链接的记录请求确认 fetch + write。

- [ ] **Step 5: Commit**

---



## Task 13: DocViewer 高亮

**Files:**

- Modify: `frontend/src/components/DocViewer.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: DocViewer 添加 highlightText prop**

在正文渲染后，用 `useEffect` 查找包含 `highlightText` 的 DOM 节点，`scrollIntoView` 并添加 `.highlight` 样式。

- [ ] **Step 2: App 维护 highlight 状态**

```typescript
const [highlightText, setHighlightText] = useState<string | undefined>();
<DocViewer path={selectedPath} highlightText={highlightText} onBack={...} />
```

- [ ] **Step 3: Commit**

---



## Task 14: 集成测试与文档收尾

**Files:**

- Modify: `backend/tests/test_api.py`
- Modify: `backend/tests/conftest.py`
- Modify: `README.md`

- [ ] **Step 1: 更新 conftest 支持 tool_responses**

```python
llm = FakeLLMClient(
    tool_responses=[
        {"content": None, "tool_calls": [{"id": "1", "name": "search_kb", "arguments": {"query": "docker"}}]},
        {"content": "docker 用于容器", "tool_calls": []},
    ],
    embed_dim=8,
)
```

- [ ] **Step 2: 添加 SSE 集成测试**

验证事件序列含 `ts`、`tool_start`、`done`；验证 `duration_ms` 字段存在。

- [ ] **Step 3: 运行全量测试**

```bash
cd backend && python -m pytest -v
cd frontend && npm run build
```

- [ ] **Step 4: 更新 README**

在「配置」章节说明搜索 API Key 和 Agent 行为简述。

- [ ] **Step 5: Commit**

```bash
git add backend/tests/ README.md
git commit -m "test: add agent SSE integration tests and update docs"
```

---



## Spec 覆盖自检


| Spec 要求                     | 对应 Task                |
| --------------------------- | ---------------------- |
| 统一 Agent 替代 intent 分流       | Task 7, 8              |
| 6 种工具                       | Task 6                 |
| 有限并行 + 批次事件                 | Task 7                 |
| 多搜索提供商                      | Task 4                 |
| URL 抓取 + SSRF               | Task 3                 |
| SSE 时间线 + ts + duration_ms  | Task 5, 7, 8           |
| 来源点击三分流                     | Task 11, 12, 13        |
| 对话 timeline 持久化             | Task 9                 |
| 显式口令 force_write / no_write | Task 6 prompts, Task 8 |
| 旧消息兼容                       | Task 12                |
| ingest/ask 保留               | Task 8                 |
| 验收标准 1-7                    | Task 14 手动 + 自动测试      |


无遗漏项。

---



## 建议实施顺序

```
Task 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14
```

后端 Task 1-9 可先完成并 `pytest` 全绿，再推进前端 Task 10-13。