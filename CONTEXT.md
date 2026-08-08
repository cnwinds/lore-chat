# Lore Chat — 工程上下文

面向 AI 与贡献者的模块地图：写代码前先确认 **seam**（边界），避免在 HTTP / Agent / Organizer 之间重复编排。

## 分层（由外到内）

| 层 | 路径 | 职责 |
|----|------|------|
| HTTP | `backend/app/api/routes.py` | 鉴权、DTO、StreamingResponse；**不**解析 Agent SSE |
| 聊天 | `backend/app/engine/chat/` | `TurnExecutionHub`（begin/ensure/观测/stop 生命周期）、`ChatSessionRunner`（HTTP 薄 facade + ephemeral）、时间线、SSE；持久回合可发 `timeline_state` 投影 |
| Agent | `backend/app/engine/agent/` | `AgentOrchestrator`（adapter）、`AgentToolLoop`（LLM+工具循环）、`tool_catalog`、`tool_impl/*`（执行）、`tools.py`（`ToolRegistry.execute` / `rebind` / `interrupt_runtime`） |
| 会话 | `backend/app/engine/conversations.py` + `conversation/outbox.py` + `conversation/memory_schedule.py` | SQLite 消息/turn；派生 outbox；**记忆抽取调度**（dirty/CAS/idle/enqueue）在 `MemoryExtractSchedule` |
| 知识写入 | `backend/app/engine/knowledge_writer.py` | 路径 + git + 索引 + changelog **唯一写入 seam**；意图级 `persist_document` / `import_entry`（`allow_binary`）/ `read_entry_bytes` / `move_entry` / `delete_entry`；非 MD 准入经 `assert_non_md_asset_allowed`；Merge/Agent 勿自组 drop_index |
| 沙箱 | `backend/app/engine/sandbox/` | `SandboxRuntime` 端口；`SandboxCommandGate`（高风险确认）；`KbSandboxExchange`（stage/publish）；`SandboxTools` 为薄 tool adapter |
| 文档成文 | `backend/app/engine/document_synthesis.py` | 归档/合并/入库合并的 LLM 成文；Organizer 与 MergeWorkflow 共用 |
| 会话定稿观察 | `backend/app/engine/memory/session_observe.py` | dirty / idle / extract / SlotResolver / CAS **deep module**（`SessionMemoryObserve`；`MemoryWorker` 为兼容别名） |
| 记忆写入 | `backend/app/engine/memory/resolver.py` + `service.py` | 全部突变经 `MemoryService` → 唯一 `SlotResolver`（remember/confirm/edit/correct/forget） |
| 知识库树 HTTP | `backend/app/engine/kb_tree_service.py` | import/move/delete + protected + `index_revision.bump` |
| 归位 | `backend/app/engine/placement.py` | LLM 决定 new/merge 与 `rel_path` |
| 整理 | `backend/app/engine/organizer.py` | 录入/归档正文合成 + `PlacementPlanner` + `KnowledgeWriter` |
| 文档合并 | `backend/app/engine/merge_workflow.py` | 多源合并、审阅会话；HTTP 经 `Container.merge_workflow` |
| Pending 决议 | `backend/app/engine/pending_resolver.py` | `/questions/.../resolve` 编排 seam |
| 存储 | `backend/app/storage/` | `KnowledgeRepo`、`kb_paths` |

## 依赖注入

`backend/app/deps.py` 的 `Container` 持有各运行时模块；构图拆为子图（`deps_index.py` / `deps_memory.py` / `deps_agent.py`），`apply_settings` 经子图 `rebind_llm` 热更新。

- `knowledge_writer` → 注入 `Organizer`、`ToolRegistry`、`MemoryService`（记忆投影不入 KB 检索）；**须为同一实例**
- `chat_runner: ChatSessionRunner` → 持有 `turn_hub`；`POST /chat` 经 `begin_persisted_turn` + `observe_turn`（生命周期在 hub）
- `derivation_worker` / `memory_worker`（`SessionMemoryObserve`）→ 消费 `ConversationStore.claim_outbox`

`apply_settings()`：`IndexSubgraph.apply_settings`（检索 tunables）+ 各子图 `rebind_llm` + `AgentSubgraph.publish`（同步 Container facade）。

## 知识库路径约定

所有**新建/归档**到 KB 的入口必须带 **`directory` + `filename`**（`.md`）：

- Agent：`write_kb`、`summarize_conversation`（见 `tool_catalog.py`）
- HTTP：`POST /api/conversations/{id}/summarize` body 同形
- 校验与拼接：`kb_paths.join_kb_path` / `KnowledgeWriter.resolve_location`

`move_entry` 使用 `from_path` + `to_directory` + `to_filename`。

维护性全量文档索引重建：`backup/reindex.reindex_all` → `KnowledgeWriter.reindex_markdown_body`（不写 changelog）。

## 聊天持久化

1. `begin_turn` → 写入用户消息 + running turn  
2. `TurnExecutionHub.ensure_running` → 进程内 Task 跑 Agent；SSE 仅 `subscribe` 观测（断开不取消执行）  
3. `done` / 显式 `POST /api/chat/stop` / 启动孤儿回收 → `finalize_turn`  
4. Outbox：`index_fts` / `index_vector` / `session_observe_memory`（经 `SessionMemoryObserve`；用户消息只打 `memory_dirty`，空闲或归档后入队；成功抽取递增 `memory_extract_revision`；按条 `observe_memory` / `MemoryIntake` 已废除）
5. 记忆面板 API：`/api/memory/facts`（列表 / confirm / reject / edit / forget）；设置页「记忆」页签；写路径与自动抽取共用 `SlotResolver`

无 `conversation_id` 时仅 `stream_ephemeral`，不落库（仍跟连接走）。

## 运行数据（Docker）

- Compose：`docker/docker-compose.yml`（项目根执行：`docker compose -f docker/docker-compose.yml --project-directory docker --env-file .env`）
- **可选执行能力**：叠加 `docker/docker-compose.sandbox.yml` 启动 OpenSandbox；`SANDBOX_ENABLED` / `GET /api/health` → `capabilities.sandbox`。启用后 Agent 可调用 `sandbox_run` / `sandbox_list_dir` / `sandbox_read_file` / `publish_from_sandbox`（SSE `tool_progress`）。见 [ADR 2026-08-06](docs/adr/2026-08-06-opensandbox-runtime.md)
- 知识库卷：`docker/data/knowledge/`
- 备份卷：`docker/data/backups/`

## 进一步阅读

- [ADR：引擎模块 seam（2026-08-04）](docs/adr/2026-08-04-engine-module-seams.md)
- [ADR：多文档合并仅 UI（2026-08-05）](docs/adr/2026-08-05-merge-ui-only.md)
- 产品规格：`docs/superpowers/specs/`

## Language（对话与知识库）

**发送队列**：流式输出时输入框仍可编辑；发送进入按会话隔离的队列（`localStorage`，上限 20）。默认时机 **defer**（当前 turn `done` 后 FIFO/`begin_turn`）；可改为 **inject**（不中断 turn，在 tool 结果回写后、下次 LLM 前插入；无窗口则降级 defer）。「与下一条合并」将同策略相邻项合成一条用户消息。空闲且队列空则直发；停止只中断当前 turn；失败暂停刷队；若回合以未回答的 `ask_user` 征询结束则暂停刷队，待用户作答后再续。前端编排在 `useOutboundOrchestrator`；策略纯函数在 `outboundQueue`。
_Avoid_: 流式中锁死输入；同会话并行多个 running turn；inject 打断当前生成；征询未答时自动刷队；在 `Chat.tsx` 再堆 flush/inject 状态机

**沙箱确认**：高风险 `sandbox_run` 在 trust_mode 关闭时经 `SandboxCommandGate` 建 Pending；用户批准后由 `PendingResolver` 后端代跑（不依赖模型再调工具）。
_Avoid_: 在 Organizer / KB 摄入路径解析 `sandbox_confirm`

**文档托盘**：用户在发送前选中的知识库上下文集合；项为带类型的 `{ path, kind }`，持久化在消息的 `doc_context` 中。可含普通文档与 Skill 根等。
_Avoid_: 附件托盘（与 `attachments/` 二进制附件区分）；仅用无类型路径列表表达 Skill

**主文档**：托盘内用于默认 `edit_doc` 目标的普通 Markdown 文档。Skill 包（`skill_root`）不可作主文档；用户明确指定路径时仍可 `edit_doc`（含某 Skill 的 `SKILL.md`）。
_Avoid_: 把 Skill 根当作可编辑文档

**Skill 激活**：仅当托盘含 `skill_root` 时，在本轮 system 对该包注入元信息与 `SKILL.md` 入口正文（首窗与 `read_doc` 默认 limit 对齐，约 3000 字；不足则全文）；不预载 `references/` 等子资源。
_Avoid_: 全量注入；对普通 `document` 路径做 Skill 激活

**Skill 包发现**：用户点选侧栏某文件夹后，自该目录起**递归**找出所有「目录内直接含 `SKILL.md`」的包根；经**勾选确认层**（列出候选路径，用户选择）后以若干 `skill_root` 写入托盘。点选目录自身含 `SKILL.md` 时，候选列表须包含该目录。未发现任何包时提示用户，不写入托盘。前端编排在 `useSkillTrayAttach`。
_Avoid_: 不经确认自动塞满托盘；只扫描一层；在 `App.tsx` 再堆发现/确认状态机

**托盘项类型（kind）**：`document`（普通 Markdown）与 `skill_root`（Skill 包根目录）。**仅 `skill_root` 触发 Skill 激活**；`document` 永不因 Skill 规则激活。历史纯字符串路径读作 `document`；不重放补做 Skill 激活。
_Avoid_: 单文件 Skill；对旧会话做全库迁移

**多 Skill 并存**：同一轮可挂多个 `skill_root`；各 Skill 分段注入 system，顺序与托盘一致；与用户消息冲突以用户消息为准；Skill 之间冲突则合并取交集或向用户澄清。
_Avoid_: 每轮仅允许一个 Skill（除非产品另行限制）
