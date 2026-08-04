# Lore Chat — 工程上下文

面向 AI 与贡献者的模块地图：写代码前先确认 **seam**（边界），避免在 HTTP / Agent / Organizer 之间重复编排。

## 分层（由外到内）

| 层 | 路径 | 职责 |
|----|------|------|
| HTTP | `backend/app/api/routes.py` | 鉴权、DTO、StreamingResponse；**不**解析 Agent SSE |
| 聊天 | `backend/app/engine/chat/` | `ChatSessionRunner`、时间线累积、SSE 解析 |
| Agent | `backend/app/engine/agent/` | `AgentOrchestrator`（adapter）、`AgentToolLoop`（LLM+工具循环）、`tool_catalog`、`tools.py`（执行） |
| 会话 | `backend/app/engine/conversations.py` + `conversation/outbox.py` | SQLite 消息/turn；派生任务队列 |
| 知识写入 | `backend/app/engine/knowledge_writer.py` | 路径 + git + 索引 + changelog **唯一写入 seam**；`import_entry` / `move_entry` / `delete_entry`（含附件） |
| 知识库树 HTTP | `backend/app/engine/kb_tree_service.py` | import/move/delete + protected + `index_revision.bump` |
| 归位 | `backend/app/engine/placement.py` | LLM 决定 new/merge 与 `rel_path` |
| 整理 | `backend/app/engine/organizer.py` | 录入/归档/合并的正文合成 + 调用 `PlacementPlanner` + `KnowledgeWriter` |
| 存储 | `backend/app/storage/` | `KnowledgeRepo`、`kb_paths` |

## 依赖注入

`backend/app/deps.py` 的 `Container` 持有：

- `knowledge_writer` → 注入 `Organizer`、`ToolRegistry`、`MemoryService`（记忆投影不入 KB 检索）
- `chat_runner: ChatSessionRunner` → 注入 `agent` + `conversations`；路由用 `c.chat_runner`
- `derivation_worker` / `memory_worker` → 消费 `ConversationStore.claim_outbox`

`apply_settings()` 会重建 `chat_runner`（agent/llm 热更新后仍指向同一 conversations）。

## 知识库路径约定

所有**新建/归档**到 KB 的入口必须带 **`directory` + `filename`**（`.md`）：

- Agent：`write_kb`、`summarize_conversation`（见 `tool_catalog.py`）
- HTTP：`POST /api/conversations/{id}/summarize` body 同形
- 校验与拼接：`kb_paths.join_kb_path` / `KnowledgeWriter.resolve_location`

`move_doc` 使用 `from_path` + `to_directory` + `to_filename`。

维护性全量文档索引重建：`backup/reindex.reindex_all` → `KnowledgeWriter.reindex_markdown_body`（不写 changelog）。

## 聊天持久化

1. `begin_turn` → 写入用户消息 + running turn  
2. `ChatSessionRunner.stream_and_persist` → 累积 SSE → `finalize_turn`  
3. Outbox：`index_fts` / `index_vector` / `observe_memory`

无 `conversation_id` 时仅 `stream_ephemeral`，不落库。

## 运行数据（Docker）

- Compose：`docker/docker-compose.yml`（项目根执行：`docker compose -f docker/docker-compose.yml --project-directory docker --env-file .env`）
- 知识库卷：`docker/data/knowledge/`
- 备份卷：`docker/data/backups/`

## 进一步阅读

- [ADR：引擎模块 seam（2026-08-04）](docs/adr/2026-08-04-engine-module-seams.md)
- 产品规格：`docs/superpowers/specs/`
