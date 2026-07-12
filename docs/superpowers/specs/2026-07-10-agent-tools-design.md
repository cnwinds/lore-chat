# Lorechat Agent 工具能力设计文档

- 日期：2026-07-10
- 状态：设计已确认，待用户审阅 spec 后编写实现计划
- 前置文档：[2026-07-09-chat-knowledge-base-design.md](./2026-07-09-chat-knowledge-base-design.md)

## 1. 背景与目标

### 1.1 现状问题

当前 lorechat 将用户消息分为 `remember`（录入）和 `recall`（问答）两条独立流水线：

- 用户说「帮我记录」并附上 GitHub 链接时，系统**只保存原始文本**，不抓取、不解析链接内容。
- 问答只能检索本地知识库，无法联网搜索或访问网页。
- 用户需主动说「记录」才能写入知识库，不符合「边聊边沉淀」的产品愿景。

### 1.2 目标

将 lorechat 升级为**统一 Agent**：用户只管聊天解决问题，Agent 在后台静默维护知识库。

| 维度 | 要求 |
|------|------|
| 核心任务 | 解决用户问题（优先本地知识库，不足时搜索/抓链接） |
| 知识落库 | 静默、自动，用户无感知；可随时在侧边栏查看整理结果 |
| 工具能力 | 检索本地库、读取文档、搜索网页、抓取 URL、写入知识库 |
| 交互风格 | 时间线式输出，可折叠工具步骤，来源可点击，历史会话保留完整时间线 |
| 显式口令 | 自然对话为主；支持「帮我记录」「别保存」「只搜不写」「搜一下」等 override |
| 并行执行 | 无依赖的读操作支持有限并行；写入操作保持串行 |

## 2. 方案选型

采用 **方案 C：统一 Agent + 复用现有引擎**。

```
用户消息
  → AgentOrchestrator（大模型 + tool calling，SSE 流式）
      工具层：
        search_kb()    → Retriever.search()
        read_doc()     → KnowledgeRepo.read()
        fetch_url()    → WebFetcher（新）
        web_search()   → WebSearch 多提供商（新）
        write_kb()     → Organizer.ingest_text()
        ask_user()     → PendingStore
  → 时间线事件流（每条带时间戳）→ 前端按序渲染
  → 对话持久化（timeline + sources，历史可点击）
```

不采用纯双阶段（先答后写），因为用户期望单轮对话内可「先搜→再写→再答」。

## 3. Agent 决策原则

写入 system prompt，指导大模型行为：

1. **首要任务**：解决用户当前问题。
2. **检索优先级**：本地知识库 → 用户消息中的 URL → 网页搜索（本地无结果或用户明确要求时）。
3. **落库策略（混合）**：
   - 默认克制：闲聊、试探性讨论不落库。
   - 高价值信号积极落库：项目启动、技术方案、教程链接、排障结论等。
   - 重复/过时内容由 Agent 后续合并修订（复用 Organizer 决策逻辑）。
4. **显式口令**：
   - 「帮我记录」→ 强制 `write_kb`
   - 「别保存」「只搜不写」→ 禁止 `write_kb`
   - 「搜一下」「联网查」→ 强制 `web_search`
5. **低置信度落库**：`write_kb` 决策不确定时调用 `ask_user`，在对话中插入选择题（复用 PendingStore）。

## 4. 工具定义

### 4.1 工具清单

| 工具 | 输入 | 输出 | 底层 |
|------|------|------|------|
| `search_kb` | `query: str`, `k?: int` | 片段列表（path, excerpt, score） | `Retriever.search()` |
| `read_doc` | `path: str` | 文档全文 | `KnowledgeRepo.read()` |
| `fetch_url` | `url: str` | title, markdown 正文, snippet | `WebFetcher` |
| `web_search` | `query: str`, `k?: int` | 结果列表（title, url, snippet） | `WebSearch` |
| `write_kb` | `text: str`, `context?: str` | status, rel_path, message | `Organizer.ingest_text()` |
| `ask_user` | `question: str`, `options: list` | question_id | `PendingStore` |

### 4.2 并行调用规则

**可并行（同一批次）：**

- 多个 `search_kb`（不同 query）
- 多个 `fetch_url`（不同 URL）
- 多个 `read_doc`（不同 path）
- `search_kb` + `web_search`（互相独立时）
- 以上任意只读工具的组合

**必须串行：**

- `write_kb` 及之后依赖其结果的步骤
- `ask_user`（需等用户回复）
- 有数据依赖的工具链（如先 `fetch_url` 再 `write_kb`）

**实现：**

```python
# 一轮 LLM 返回多个 tool_calls 时
if all(can_parallelize(tc) for tc in tool_calls):
    results = await asyncio.gather(*[run_tool(tc) for tc in tool_calls])
else:
    # 拆批：先并行读，再串行写
```

**配置：**

```env
AGENT_PARALLEL_TOOLS=true    # 默认开启
AGENT_MAX_PARALLEL=4         # 单批最多并行 4 个
AGENT_MAX_TOOL_CALLS=8       # 单轮对话最多 8 次 tool call
```

### 4.3 网页搜索多提供商

```env
TAVILY_API_KEY=
SERPER_API_KEY=
BRAVE_SEARCH_API_KEY=
SEARCH_PROVIDER_ORDER=tavily,serper,brave
```

- 统一接口 `WebSearchProvider.search(query, k) -> list[SearchResult]`
- 按 `SEARCH_PROVIDER_ORDER` 顺序，使用第一个已配置 API Key 的提供商
- 未配置任何搜索 API 时，工具返回明确错误，Agent 告知用户

### 4.4 URL 抓取

```env
FETCH_URL_TIMEOUT=15         # 秒
FETCH_URL_MAX_BYTES=102400   # 100KB
```

- `httpx` 异步请求 + `markitdown` 或 `readability` 转 Markdown
- 拒绝私有 IP / localhost（SSRF 防护）
- 失败时返回错误摘要，不中断 Agent 循环

## 5. SSE 事件协议

`POST /api/chat` 改为 `text/event-stream`，每个事件**必须携带 ISO 8601 时间戳**。

### 5.1 事件类型

| event | 用途 |
|-------|------|
| `tool_start` | 单个工具开始 |
| `tool_result` | 单个工具完成 |
| `parallel_batch_start` | 并行批次开始 |
| `parallel_batch_end` | 并行批次结束 |
| `text_delta` | 回答正文增量 |
| `ask_user` | 需用户选择 |
| `done` | 本轮结束，附汇总 sources |
| `error` | 错误，前端显示重试 |

### 5.2 事件格式

所有事件的 `data` 字段为 JSON，**必须包含 `ts` 字段**（ISO 8601，如 `2026-07-10T10:44:32+08:00`）。

```json
// tool_start
{"ts":"2026-07-10T10:44:32+08:00","id":"t1","tool":"search_kb","label":"检索本地知识库","input":{"query":"lorechat"}}

// tool_result
{"ts":"2026-07-10T10:44:33+08:00","id":"t1","tool":"search_kb","summary":"找到 0 条相关内容","sources":[],"duration_ms":820}

// parallel_batch_start
{"ts":"2026-07-10T10:44:33+08:00","batch_id":"b1","tools":["fetch_url","fetch_url"]}

// parallel_batch_end
{"ts":"2026-07-10T10:44:36+08:00","batch_id":"b1","duration_ms":2800}

// text_delta
{"ts":"2026-07-10T10:44:37+08:00","delta":"lorechat 是一个对话式知识库项目…"}

// done
{"ts":"2026-07-10T10:44:38+08:00","sources":[...],"total_duration_ms":6200}
```

### 5.3 时间戳用途

1. **前端展示**：工具块、正文旁显示发生时间（如 `10:44`）；用户可判断对话节奏。
2. **使用统计**：`duration_ms` 记录工具耗时；`total_duration_ms` 记录整轮耗时；后续可汇总分析。
3. **历史回放**：持久化的 timeline 保留每条事件的 `ts`，历史会话按原始时间展示。

### 5.4 时间线顺序原则

- 事件按实际发生顺序推送，前端按序渲染。
- 并行批次内：先 `parallel_batch_start`，各 `tool_result` 完成即推送（不等整批），最后 `parallel_batch_end`。
- `text_delta` 在依赖的工具完成后输出，不合并到最后一次性展示。

## 6. 来源引用与点击行为

### 6.1 SourceRef 类型

```typescript
type SourceRef =
  | { type: "kb"; path: string; excerpt?: string; line?: number }
  | { type: "web"; url: string; title: string; snippet: string }
  | { type: "search"; provider: string; url: string; title: string; snippet: string };
```

### 6.2 点击行为（智能分流）

| 来源类型 | 点击行为 |
|----------|----------|
| `kb`（本地文档） | 侧边栏 `DocViewer` 打开，高亮 `excerpt` 对应段落 |
| `web`（已抓取的外链） | 新标签页打开原始 URL |
| `search`（仅搜索摘要） | 弹层展示 `snippet`；若有 URL 提供「打开原文」链接 |

历史会话中的来源按钮行为与实时对话一致。

## 7. 前端时间线 UI

### 7.1 消息结构

```typescript
type TimelineBlock =
  | { type: "tool"; id: string; tool: string; label: string;
      ts: string; status: "running" | "done";
      summary?: string; sources?: SourceRef[]; duration_ms?: number }
  | { type: "parallel"; batch_id: string; ts: string;
      children: TimelineBlock[]; duration_ms?: number }
  | { type: "text"; ts: string; content: string };

type AssistantMessage = {
  role: "assistant";
  ts: string;                    // 助手消息开始时间
  timeline: TimelineBlock[];
  sources: SourceRef[];
};
```

### 7.2 渲染规则

- **工具块**：默认折叠，显示标签 + 摘要 + 时间；展开看详情和来源按钮。
- **并行块**：标题「检索资料」，内含多个子工具项；子项完成即显示。
- **正文块**：完整展示，不折叠；流式追加 `content`。
- **来源按钮**：附在对应工具结果或正文末尾。
- **write_kb 完成后**：触发 `onSidebarRefresh()` 刷新文件树。

### 7.3 组件改动

| 文件 | 改动 |
|------|------|
| `Chat.tsx` | 同步 `chat()` → `chatStream()` 消费 SSE |
| `api.ts` | 新增 `chatStream()`、事件类型定义 |
| `App.tsx` | 来源点击 → `setSelectedDoc` + `setHighlight` |
| `DocViewer.tsx` | 新增 `highlightText` prop |
| 新增 `SourceChip.tsx` | 来源按钮组件 |
| 新增 `TimelineBlock.tsx` | 时间线块渲染 |
| 新增 `SearchSnippetModal.tsx` | 搜索摘要弹层 |

## 8. 对话持久化

`conversations.json` 中 assistant 消息从扁平 `text` 升级为 `timeline` 结构：

```json
{
  "role": "assistant",
  "ts": "2026-07-10T10:44:32+08:00",
  "timeline": [
    {"type": "tool", "id": "t1", "tool": "search_kb", "ts": "...", "label": "检索本地知识库", "summary": "找到 0 条", "duration_ms": 820},
    {"type": "parallel", "batch_id": "b1", "ts": "...", "children": [...], "duration_ms": 2800},
    {"type": "text", "ts": "...", "content": "lorechat 是..."}
  ],
  "sources": [{"type": "kb", "path": "projects/lorechat/start.md"}]
}
```

- 旧格式消息（仅 `text` 字段）前端兼容渲染为单个 `text` 块。
- 用户消息也记录 `ts` 字段。

## 9. API 迁移

| 端点 | 处理 |
|------|------|
| `POST /api/chat` | **改为 SSE 流式**（产品主入口） |
| `POST /api/ingest` | 保留；内部转调 Agent `force_write`；**测试/脚本灌库** |
| `POST /api/ask` | 保留；内部转调 Agent `no_write`；**测试/脚本只读问答** |
| `intent.py` | 废弃；逻辑并入 Agent system prompt |

**2026-07-12 补充：** 产品 UI 已仅用 `/chat`；ingest/ask 定位为机器同步 API（确定性 + 效率）。详见 [2026-07-12-ingest-ask-api-design.md](./2026-07-12-ingest-ask-api-design.md)。

## 10. 配置汇总

```env
# 已有
BIG_MODEL=gpt-4o
SMALL_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...

# Agent 新增
AGENT_MAX_TOOL_CALLS=8
AGENT_PARALLEL_TOOLS=true
AGENT_MAX_PARALLEL=4
FETCH_URL_TIMEOUT=15
FETCH_URL_MAX_BYTES=102400

# 搜索（配哪个用哪个）
TAVILY_API_KEY=
SERPER_API_KEY=
BRAVE_SEARCH_API_KEY=
SEARCH_PROVIDER_ORDER=tavily,serper,brave
```

## 11. 错误处理

| 场景 | 行为 |
|------|------|
| 搜索 API 未配置 | 工具返回错误摘要；Agent 告知用户可配置 Key |
| URL 抓取失败 | 工具返回错误；Agent 基于已有信息回答 |
| write_kb 低置信度 | `ask_user` 插入选择题 |
| Agent 超过 MAX_TOOL_CALLS | 强制输出当前结论并说明 |
| LLM 超时/错误 | SSE 推送 `error` 事件；前端显示重试 |
| SSRF 尝试 | `fetch_url` 拒绝并返回错误 |

## 12. 后端模块结构

```
backend/app/
├── engine/
│   ├── agent/
│   │   ├── orchestrator.py    # Agent 主循环 + tool calling
│   │   ├── tools.py           # 工具注册与执行
│   │   └── prompts.py         # system prompt
│   ├── web/
│   │   ├── fetcher.py         # URL 抓取
│   │   └── search.py          # 多提供商搜索
│   ├── organizer.py           # 复用，不改动核心逻辑
│   ├── retriever.py           # 复用
│   └── conversations.py       # 扩展消息格式
├── api/routes.py              # /chat 改 SSE
└── config.py                  # 新增配置项
```

## 13. 测试策略

| 层级 | 内容 |
|------|------|
| 单元测试 | WebFetcher（mock httpx）、WebSearch（mock API）、工具并行/串行分派 |
| 集成测试 | AgentOrchestrator + FakeLLMClient 模拟 tool calling 循环 |
| API 测试 | SSE 事件序列、时间戳字段、错误路径 |
| 前端 | TimelineBlock 渲染、来源点击、旧消息兼容 |

## 14. 不在本次范围

- 后台「园丁」Agent 定期巡检整理（见 2026-07-09 设计文档 §6.3）
- 大模型审核 Organizer 决策（§6.1 第 5 步）
- 桌面 Spotlight / 微信等额外入口
- 搜索 API 用量计费/statistics 仪表盘（仅记录 `duration_ms`，不做 UI）

## 15. 验收标准

1. 用户发送「开始开发 lorechat，https://github.com/cnwinds/lore-chat，帮我记录」→ Agent 抓取 README、整理写入 `projects/lorechat/start.md`，对话时间线展示各步骤及时间戳。
2. 用户提问本地库有的内容 → 优先 `search_kb` 回答，附本地来源按钮，点击侧边栏预览高亮。
3. 用户说「搜一下 XXX」→ 调用 `web_search`，来源可点击。
4. 用户说「别保存」→ 本轮不调用 `write_kb`。
5. 多个 URL 同时出现 → 并行 `fetch_url`，时间线显示并行批次。
6. 历史会话打开 → 时间线、来源按钮、时间戳完整可交互。
7. 未配置搜索 API → Agent 明确告知，不崩溃。
