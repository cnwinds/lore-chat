# ADR 2026-08-04：引擎模块 seam 拆分

## 状态

已采纳（2026-08-04）

## 背景

架构审查发现：

1. 知识库写入（路径、git commit、全文/向量索引、changelog）分散在 `ToolRegistry` 与 `Organizer`，caller 易漏步骤或路径不一致。
2. `routes.py` 内嵌 SSE 解析与时间线累积，与 Agent 流式语义耦合，难以单测。
3. `ConversationStore` 同时承担消息 CRUD 与 derivation outbox SQL，文件过大。
4. Organizer 内 LLM「归位」逻辑与正文合成混在一起，Agent 与 HTTP 归档难以共用同一决策。

## 决策

### 1. `KnowledgeWriter`（deep module）

- **位置**：`backend/app/engine/knowledge_writer.py`
- **对外**：`persist_document`、`save_edit`、`move_document`、`import_entry`、`move_entry`、`delete_entry`（含 Markdown 与 attachments）、`resolve_location(directory, filename)` 等
- **规则**：Organizer / ToolRegistry / HTTP **不直接**调用 `Indexer` 做落库侧效应；索引与 changelog 经 writer 完成
- **维护例外**：`backup/reindex.reindex_all` 经 `KnowledgeWriter.reindex_markdown_body` 刷新已有文档索引（不写 changelog）
- **依赖**：`Organizer` 与 `ToolRegistry` 必须由 `Container` 注入**同一** `KnowledgeWriter` 实例，禁止在模块内 `KnowledgeWriter(repo, indexer)` 回退构造

### 1b. `KbTreeService`（HTTP 编排 seam）

- **位置**：`backend/app/engine/kb_tree_service.py`
- **职责**：知识库树 REST（import/move/delete）的 protected 目录校验、`index_revision.bump()`；**不**重复索引/changelog 逻辑
- **写入**：一律委托 `KnowledgeWriter.import_entry|move_entry|delete_entry`
- **HTTP**：`routes.py` 只做 Form/Body、异常 → 状态码，经 `_kb_tree_service(request)` 获取 service

### 2. `tool_catalog` 与 `ToolRegistry` 分离

- **定义**：`backend/app/engine/agent/tool_catalog.py`（含 `select_tools`、OpenAI function schema）
- **执行**：`backend/app/engine/agent/tools.py` 仅保留 dispatch 与薄适配

### 3. `ChatSessionRunner`

- **位置**：`backend/app/engine/chat/`
- **Container 字段**：`chat_runner`
- **HTTP**：`/api/chat` 只委托 runner；ingest/ask 使用 `consume_agent_*`  helper

### 3b. `AgentToolLoop`

- **位置**：`backend/app/engine/agent/tool_loop.py`（SSE 映射在 `tool_events.py`，消息组装在 `message_builder.py`）
- **`AgentOrchestrator`** 仅负责 system layer、模式与 `select_tools`，LLM 多轮工具循环委托 `AgentToolLoop`

### 4. `DerivationOutbox`

- **位置**：`backend/app/engine/conversation/outbox.py`
- **ConversationStore** 持有 `self._outbox`，对外 API（`claim_outbox` 等）保持不变

### 5. `PlacementPlanner`

- **位置**：`backend/app/engine/placement.py`
- **Organizer** 负责 transcript 合成与 `_apply`；归位 LLM 调用在 planner

### 6. 归档 API 与 Agent 对齐

- `POST /api/conversations/{cid}/summarize` 请求体必填 `directory`、`filename`
- 与 `summarize_conversation` 工具相同，经 `forced_rel_path` 写入，不再依赖纯 LLM 猜路径

## 后果

### 正面

- 写入与聊天路径可独立测试（`test_knowledge_writer.py`、`test_kb_paths.py` 等）
- 新 HTTP 端点落库应走 `KnowledgeWriter` 或 Organizer，而不是复制索引逻辑
- 前端归档需用户确认路径（`ArchiveConversationModal`），与 Agent 行为一致

### 负面 / 迁移

- 旧客户端对 `/summarize` 的空 POST **不再兼容**；须传 JSON body
- 直接 `build_container()` 的测试需包含 `chat_runner` 字段（dataclass 必填）

## 参考

- 仓库根目录 `CONTEXT.md`
- 审查报告快照：`/tmp/architecture-review-lore-chat-20260804.html`（本地生成，非版本库）
