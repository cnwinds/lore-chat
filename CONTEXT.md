# Lore Chat — 工程上下文

面向 AI 与贡献者的模块地图：写代码前先确认 **seam**（边界），避免在 HTTP / Agent / Organizer 之间重复编排。

## 分层（由外到内）

| 层 | 路径 | 职责 |
|----|------|------|
| HTTP | `backend/app/api/routes.py` | 鉴权、DTO、StreamingResponse；**不**解析 Agent SSE |
| 聊天 | `backend/app/engine/chat/` | `TurnExecutionHub`（begin/ensure/观测/stop 生命周期）、`ChatSessionRunner`（HTTP 薄 facade + ephemeral）、时间线、SSE；持久回合：结构事件发 `timeline_state` 投影，token/进度只发增量（见 [ADR 2026-08-08](docs/adr/2026-08-08-deepen-memory-turn-tools.md) §5） |
| 模型链 | `backend/app/models/`（`candidate` / `router` / `cooldown` / `vision` / `thinking` / `catalog` / `models_dev` / `provider_models` / `effort`）+ `llm.py` | chat/utility/embed 优先级链、冷却单例、models.dev 缓存目录（包内 `data/models_dev_api.json.gz` 回退；网络拉取旁路短超时）、OpenAI 兼容 `/models` 拉取（`provider_models`；kind=`llm`/`embedding`/`image`；能力 enrich 经 `catalog`）、识图双通道；HTTP 不自建 CooldownStore / ModelsDevStore |
| 联网搜索 | `backend/app/engine/web/`（`search_providers` / `search_router` / `search_backends` / `search.py`） | 搜索提供商有序链、与模型同算法的冷却 failover；HTTP 不自建 search CooldownStore |
| 生图 | `backend/app/engine/imagegen/`（`providers` / `router` / `backends` / `service`）+ Agent `generate_image` | 多厂商薄 adapter、有序链 + 隔离冷却；权威身份为 KB 相对路径；见 [ADR 2026-08-12](docs/adr/2026-08-12-image-generation-providers.md) |
| Agent | `backend/app/engine/agent/` | `AgentOrchestrator`（adapter）、`AgentToolLoop`（LLM+工具循环）、`tool_catalog`、`tool_impl/*`（执行）、`tools.py`（`ToolRegistry.execute` / `rebind` / `interrupt_runtime`） |
| 会话 | `conversations.py` + `conversation/*` | SQLite 消息/turn；outbox；`MemoryExtractSchedule`；`ConversationTranscript`；`ConversationDeletionWorkflow`；`ConversationMessageGraph`；`ConversationSummaryLedger`（`store.summaries`）；`ConversationSystemEvents`（`store.system_events`）；其余 store 兼容委托逐步收口 |
| 知识写入 | `backend/app/engine/knowledge_writer.py` | 路径 + git + 索引 + changelog **唯一写入 seam**；意图级 `persist_document` / `import_entry`（`allow_binary`）/ `read_entry_bytes` / `move_entry` / `delete_entry`；非 MD 准入经 `assert_non_md_asset_allowed`；Merge/Agent 勿自组 drop_index |
| 沙箱 | `backend/app/engine/sandbox/` | `SandboxRuntime` 端口；`SandboxCommandGate`（高风险确认）；`KbSandboxExchange`（stage/publish）；`SandboxTools` 为薄 tool adapter |
| 文档成文 | `backend/app/engine/document_synthesis.py` | 归档/合并/入库合并的 LLM 成文；Organizer 与 MergeWorkflow 共用 |
| 会话定稿观察 | `backend/app/engine/memory/session_observe.py` | dirty / idle / extract / SlotResolver / CAS **deep module**（`SessionMemoryObserve`；`MemoryWorker` 为兼容别名） |
| 记忆写入 | `backend/app/engine/memory/resolver.py` + `service.py` | 全部突变经 `MemoryService` → 唯一 `SlotResolver`（remember/confirm/edit/correct/forget） |
| 知识库树 HTTP | `backend/app/engine/kb_tree_service.py` | import/move/delete + protected + `index_revision.bump` |
| 归位 | `backend/app/engine/placement.py` | LLM 决定 new/merge 与 `rel_path` |
| 整理 | `backend/app/engine/organizer.py` | 录入编排 + `PlacementPlanner` + `KnowledgeWriter`；归档/`AgentChoiceResolution` 薄委托 |
| 会话归档 | `backend/app/engine/conversation_archive.py` | 通读 transcript → 分段合成 → 强制路径落库（镜像 `MergeWorkflow`） |
| 文档合并 | `backend/app/engine/merge_workflow.py` | 多源合并、审阅会话；HTTP 经 `Container.merge_workflow` |
| 记忆时间线压缩 | `backend/app/engine/memory/dialogue_timeline_pack.py` | 会话级抽取输入的预算/头尾打包；`session_extractor` 只做 SlotAction |
| Pending 决议 | `backend/app/engine/pending_resolver.py` | `/questions/.../resolve` 编排 seam |
| 存储 | `backend/app/storage/` | `KnowledgeRepo`、`kb_paths`、`kb_media_paths`（聊天上传/生图目录约定） |

## 依赖注入

`backend/app/deps.py` 的 `Container` 持有各运行时模块；构图拆为子图（`deps_index.py` / `deps_memory.py` / `deps_agent.py`），`apply_settings` 经子图 `rebind_llm` 热更新。

- `knowledge_writer` → 注入 `Organizer`、`ToolRegistry`、`MemoryService`（记忆投影不入 KB 检索）；**须为同一实例**
- `ImageGen` → 依赖同一 `knowledge_writer` 与 `image_cooldown`（落盘与 failover；见 ADR 2026-08-12）
- `model_cooldown: CooldownStore` → 与 `OpenAILLMClient.cooldown` **须为同一实例**（admin 清冷却 / 选模共用）
- `search_cooldown: CooldownStore` → 与 `WebSearch.cooldown` **须为同一实例**（admin 清冷却 / 搜索 failover 共用；落盘 `.kb/search_cooldown.json`，与 model 冷却隔离）
- `image_cooldown: CooldownStore` → 与 `ImageGen.cooldown` **须为同一实例**（admin 清冷却 / 生图 failover 共用；落盘 `.kb/image_cooldown.json`）
- `models_dev: ModelsDevStore` → 与 enrich/admin 目录查询 **须为同一实例**（`shared_models_dev_store` + `set_active_models_dev_store`）
- `chat_runner: ChatSessionRunner` → 持有 `turn_hub`；`POST /chat` 经 `begin_persisted_turn` + `observe_turn`（生命周期在 hub）
- `derivation_worker` / `memory_worker`（`SessionMemoryObserve`）→ 消费 `ConversationStore.claim_outbox`

`apply_settings()`：`IndexSubgraph.apply_settings`（检索 tunables）+ 各子图 `rebind_llm` + `AgentSubgraph.publish`（同步 Container facade）。

## 知识库路径约定

所有**新建/归档**到 KB 的入口必须带 **`directory` + `filename`**（`.md`）：

- Agent：`write_doc`、`summarize_conversation`（见 `tool_catalog.py`）
- HTTP：`POST /api/conversations/{id}/summarize` body 同形
- 校验与拼接：`kb_paths.join_kb_path` / `KnowledgeWriter.resolve_location`

`move_entry` 使用 `from_path` + `to_directory` + `to_filename`。

维护性全量文档索引重建：`backup/reindex.reindex_all` → `KnowledgeWriter.reindex_markdown_body`（不写 changelog）。

## 聊天持久化

1. `begin_turn` → 写入用户消息 + running turn  
2. `TurnExecutionHub.ensure_running` → 进程内 Task 跑 Agent；SSE 仅 `subscribe` 观测（断开不取消执行）  
3. `done` / 显式 `POST /api/chat/stop` / 启动孤儿回收 → `finalize_turn`  
4. Outbox：`index_fts` / `index_vector` / `session_observe_memory`（经 `SessionMemoryObserve`；用户消息只打 `memory_dirty`，空闲或归档后入队；成功抽取递增 `memory_extract_revision`；按条 `observe_memory` / `MemoryIntake` 已废除）
5. 记忆面板 API：`/api/memory/facts`（列表 / confirm / reject / edit / forget）；知识库侧栏「记忆」浮窗；写路径与自动抽取共用 `SlotResolver`

无 `conversation_id` 时仅 `stream_ephemeral`，不落库（仍跟连接走）。

## 运行数据（Docker）

- **一键拉取（小白）**：单文件启动器 [`deploy/lorechat.sh`](deploy/lorechat.sh) / [`deploy/lorechat.ps1`](deploy/lorechat.ps1)（由 [`scripts/gen-deploy-launchers.py`](scripts/gen-deploy-launchers.py) 生成；运行时在脚本旁写出 compose / 沙箱配置）。数据默认 `./data/knowledge/`、`./data/backups/`。镜像 tag：`LORECHAT_IMAGE_TAG`（`latest` 或 `v0.1.0` 这类，与 git tag 相同）；发版流程见 [AGENTS.md](AGENTS.md#二版本发布)
- **源码构建（开发者）**：`docker/docker-compose.yml` + 根 `./lorechat.sh start --chat|--work`（共用 [`scripts/lorechat-compose-lib.sh`](scripts/lorechat-compose-lib.sh)）
- **可选执行能力**：叠加 sandbox compose；`SANDBOX_ENABLED` / `GET /api/health` → `capabilities.sandbox`。见 [ADR 2026-08-06](docs/adr/2026-08-06-opensandbox-runtime.md)
- OpenSandbox 配置源：`docker/opensandbox/config.toml`（嵌入预构建启动器；开发路径挂载 `docker/opensandbox/`）
- 镜像 pin：`scripts/opensandbox-pins.sh` 由 `gen-deploy-launchers.py` 从 config.toml + sandbox compose 生成；根 `lorechat-compose-lib.sh` source 该文件

## 进一步阅读

- [ADR：引擎模块 seam（2026-08-04）](docs/adr/2026-08-04-engine-module-seams.md)
- [ADR：多文档合并仅 UI（2026-08-05）](docs/adr/2026-08-05-merge-ui-only.md)
- 产品规格：`docs/superpowers/specs/`

## Language（对话与知识库）

**发送队列**：流式输出时输入框仍可编辑；发送进入按会话隔离的队列（`localStorage`，上限 20）。默认时机 **defer**（当前 turn `done` 后 FIFO/`begin_turn`）；可改为 **inject**（不中断 turn，在 tool 结果回写后、下次 LLM 前插入；无窗口则降级 defer）。「与下一条合并」将同策略相邻项合成一条用户消息。空闲且队列空则直发；停止只中断当前 turn；失败暂停刷队；若回合以未回答的 `ask_user` 征询结束则暂停刷队，待用户作答后再续。前端编排在 `useOutboundOrchestrator`；策略纯函数在 `outboundQueue`。
_Avoid_: 流式中锁死输入；同会话并行多个 running turn；inject 打断当前生成；征询未答时自动刷队；在 `Chat.tsx` 再堆 flush/inject 状态机

**沙箱确认**：高风险 `sandbox_run` 在 trust_mode 关闭时经 `SandboxCommandGate` 建 Pending；用户批准后由 `PendingResolver` 后端代跑（不依赖模型再调工具）。
_Avoid_: 在 Organizer / KB 摄入路径解析 `sandbox_confirm`

**文档托盘（工作托盘）**：用户 Ctrl+单击侧栏**文件或目录**（顶层「技能」除外）加入；项为 `{ path, kind: "document" }`，持久化在 `doc_context`。含义：本轮主要针对这些路径工作（目录=在该目录范围内作业）。编排在 `useComposerPreviewBridge`。
_Avoid_: 附件托盘；用托盘表达 Skill 启用；Ctrl+单击非「技能」根时打开启用窗；在 `App.tsx` 再堆 pin/tray 状态机

**主文档**：托盘内用于默认 `edit_doc` 目标的普通 Markdown 文档。文档元数据用 `write_doc.meta` / `read_doc_meta` / `update_doc_meta`，调用方不感知磁盘定界。
_Avoid_: 在正文伪造 KB 元数据头

**Skill 启用集（catalog）**：跨会话保存在 `.kb/enabled_skills.json`；编排在 `useEnabledSkillsAttach`。**仅** Ctrl+单击顶层「技能」目录（或该目录右键「启用 Skill…」）→ 发现全部包 → 勾选维护默认启用集（首次无启用则默认全选，否则预勾选「候选 ∩ 已启用」）。确认后 `PUT /api/enabled-skills` **整表重写** `roots`。每轮注入 name/description（见 `[Skill 目录]`）；命中后再 `read_doc`。启用集**不进**托盘；要对某包改内容，Ctrl+单击该包目录/文件加入托盘即可。Skill 包（含 `SKILL.md`）**必须**落在「技能」目录下（发现 / 启用 / 写入硬约束）；对话 catalog 由 `ChatSessionRunner.resolve_skill_catalog` 装配。
_Avoid_: 挂载即灌入 SKILL.md 全文；子文件夹 Ctrl+单击打开启用窗；把 name/description 写入 `<<<LORE_META`；在 SYSTEM_PROMPT 与 catalog 注入重复写触发契约；在 HTTP 路由内直接编排 `EnabledSkillsStore`；作用域合并双形态 PUT

**Skill 正文头**：每个 `SKILL.md` 正文开头须有 `---` YAML，含非空 `name` 与 `description`（何时使用，语言不限）。缺头时启用/对话返回可读错误，引导用户改文件。KB 文档元数据只用 `<<<LORE_META`；正文 `---` 不作库头解析。文档预览模式将触发头拆成表格展示，正文交给编辑器；源码模式仍编辑原始 YAML；落盘保留原 header 块。
_Avoid_: 无触发头的 Skill 包；用关键词黑名单代替 description；预览里把 YAML 当普通 Markdown 渲染；用 Crepe 序列化结果覆盖掉触发头

**知识库树 viewport UI**：侧栏目录的展开态与滚动位置（hydrate / 临时露出 / 恢复 / 落盘）收在 `useKbTreeViewportUi`；`FileTree` 只渲染受控展开；存储细节在 `kbTreeUiStorage`。
_Avoid_: 用 `onExpandReady` 跨组件握手；在 `FileTree` / `Sidebar` 再拆一套展开或滚动状态机

**托盘项类型（kind）**：仅 `document`。历史消息里的 `skill_root` 读出时一律当作 document 展示；Skill 启用与激活不经托盘。
_Avoid_: 再引入托盘 Skill 专用 kind / 标签；用托盘驱动 catalog

**多 Skill 并存**：同一启用集可含多个包；catalog 分段列出；与用户消息冲突以用户消息为准；Skill 之间冲突则合并取交集或向用户澄清。
_Avoid_: 每轮仅允许一个 Skill（除非产品另行限制）
