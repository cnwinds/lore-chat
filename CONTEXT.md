# Lore Chat — 工程上下文

面向 AI 与贡献者的模块地图：写代码前先确认 **seam**（边界），避免在 HTTP / Agent / Organizer 之间重复编排。

## 分层（由外到内）

| 层 | 路径 | 职责 |
|----|------|------|
| HTTP | `backend/app/api/routes.py` | 鉴权、DTO、StreamingResponse；**不**解析 Agent SSE |
| 聊天 | `backend/app/engine/chat/` | `TurnExecutionHub`（begin/ensure/观测/stop 生命周期）、`ChatSessionRunner`（HTTP 薄 facade + ephemeral）、时间线、SSE；持久回合：结构事件发 `timeline_state` 投影，token/进度只发增量（见 [ADR 2026-08-08](docs/adr/2026-08-08-deepen-memory-turn-tools.md) §5） |
| 模型链 | `backend/app/models/`（`candidate` / `router` / `cooldown` / `vision` / `media` / `media_adapters` / `thinking` / `catalog` / `models_dev` / `provider_models` / `effort`）+ `llm.py` | chat/utility/embed 优先级链、冷却单例、models.dev 缓存目录（包内 `data/models_dev_api.json.gz` 回退；网络拉取旁路短超时）、OpenAI 兼容 `/models` 拉取（`provider_models`；kind=`llm`/`embedding`/`image`；能力 enrich 经 `catalog`）、识图/视频多模态（`vision` 签名 URL + `media` 物化 + `media_adapters` wire）；**能力唯一真相**为 `catalog.lookup_capabilities`（HTTP：`GET /api/admin/model-capabilities`；设置页 `modelCapabilities.resolveModelCaps`）；HTTP 不自建 CooldownStore / ModelsDevStore |
| 联网搜索 | `backend/app/engine/web/`（`search_providers` / `search_router` / `search_backends` / `search.py`） | 搜索提供商有序链、与模型同算法的冷却 failover；HTTP 不自建 search CooldownStore |
| 生图 | `backend/app/engine/imagegen/`（`providers` / `router` / `backends` / `service`）+ Agent `generate_image` | 多厂商薄 adapter、有序链 + 隔离冷却；权威身份为 KB 相对路径；见 [ADR 2026-08-12](docs/adr/2026-08-12-image-generation-providers.md) |
| Agent | `backend/app/engine/agent/` | `AgentOrchestrator`（adapter）、`AgentToolLoop`（LLM+工具循环；终轮明文「【征询】」提升为 `ask_user`）、`tool_catalog`、`tool_impl/*`（执行）、`tools.py`（`ToolRegistry.execute` / `rebind` / `interrupt_runtime`） |
| 会话 | `conversations.py` + `conversation/*` | SQLite 消息/turn；`role_id` 归属角色；outbox；`MemoryExtractSchedule`；`ConversationTranscript`；`ConversationDeletionWorkflow`；`ConversationMessageGraph`；`ConversationSummaryLedger`（`store.summaries`）；`ConversationSystemEvents`（`store.system_events`）；其余 store 兼容委托逐步收口 |
| 角色 | `roles.py`（`RoleStore`） | 默认通用角色 + 可创建；人设/头像/system_prompt；侧栏角色列表 + **统一时间线**见 [ADR 2026-09-09](docs/adr/2026-09-09-multi-role-shell.md) / [ADR 2026-09-10 timeline](docs/adr/2026-09-10-role-timeline.md) / [多角色产品](docs/product/multi-role.md) |
| 角色互通 | `backend/app/engine/rooms/` | Actor / Room / `RoomDelivery`（贴消息 + Wake + 入站队列）；`send_message`；群是独立现场（头像 / CRUD / 说话人气泡，角色时间线只出卡片）；群内 Assignment 账本（回执唤醒协调者、超时只叫协调者）；见 [ADR 2026-09-12](docs/adr/2026-09-12-role-rooms.md)、[ADR 2026-09-13](docs/adr/2026-09-13-group-as-stage.md)、[ADR 2026-09-14](docs/adr/2026-09-14-group-orchestration.md) |
| 聊天通道 | `backend/app/engine/channel_plugins/` | Registry / Adapter / 实例存储 / `ChannelTurnService`（验身份 → hidden role → `begin_persisted_turn`；脚本 `stream: true` 的精简 SSE 也在此投影）；`ChannelRuntime` 挂飞书 / Slack Socket Mode / 钉钉 Stream；公开 webhook 在 `/api/channels/{id}/{type}`。HTTP **不**解析 Agent SSE。类型：`script_api`、`feishu`、`slack`、`wecom`、`dingtalk`（`wechat_mp` 灰显）。群仅 @/引用才入队；群默认关沙箱直到发送者白名单。见 [聊天通道产品](docs/product/channel-plugins.md) |
| 知识写入 | `backend/app/engine/knowledge_writer.py` | 路径 + git + 索引 + changelog **唯一写入 seam**；意图级 `persist_document` / `import_entry`（`allow_binary`）/ `read_entry_bytes` / `move_entry` / `delete_entry`；新建 Skill 默认启用；删除或缺 `SKILL.md` 时从启用集去掉该包，目录搬家则改写对应 root；非 MD 准入经 `assert_non_md_asset_allowed`；Merge/Agent 勿自组 drop_index |
| 沙箱 | `backend/app/engine/sandbox/` | `RoleSandboxPool`（每角色固定 agent+PVC；`sandbox_max_roles` / 空闲 TTL 毁容器留 PVC；控制面仍一个 `opensandbox-server`）；`SandboxRuntime` 端口；`SandboxExecutionEngine`（统一 job+poll 流式、wait 预算检查点）；`SandboxCommandGate`（高风险确认，文案带角色）；`KbSandboxExchange`（stage/publish）；`SandboxTools` 按 `conversation.role_id` 取 slot，stop 不跨角色 |
| 文档成文 | `backend/app/engine/document_synthesis.py` | 归档/合并/入库合并的 LLM 成文；Organizer 与 MergeWorkflow 共用 |
| 会话定稿观察 | `backend/app/engine/memory/session_observe.py` | dirty / idle / extract / SlotResolver / CAS **deep module**（`SessionMemoryObserve`；`MemoryWorker` 为兼容别名） |
| 记忆写入 | `backend/app/engine/memory/resolver.py` + `service.py` | 全部突变经 `MemoryService` → 唯一 `SlotResolver`（remember/confirm/edit/correct/forget） |
| 知识库树 HTTP | `backend/app/engine/kb_tree_service.py` | import/move/delete + protected + `index_revision.bump` |
| 归位 | `backend/app/engine/placement.py` | LLM 决定 new/merge 与 `rel_path` |
| 整理 | `backend/app/engine/organizer.py` | 录入编排 + `PlacementPlanner` + `KnowledgeWriter`；归档/`AgentChoiceResolution` 薄委托 |
| 会话归档 | `backend/app/engine/conversation_archive.py` | 通读 transcript → 分段合成 → 强制路径落库（镜像 `MergeWorkflow`） |
| 文档合并 | `backend/app/engine/merge_workflow.py` | 多源合并、审阅会话；HTTP 经 `Container.merge_workflow` |
| 戒律升级 | `backend/app/engine/precepts_upgrade.py` | 官方稿与本地修订的三路合并；祖先 `.kb/precepts/stock.md`（缺失则从 git 找回上次官方播种稿）；干净自动写回，冲突待确认；HTTP `/api/precepts/upgrade*` |
| 记忆时间线压缩 | `backend/app/engine/memory/dialogue_timeline_pack.py` | 会话级抽取输入的预算/头尾打包；`session_extractor` 只做 SlotAction |
| Pending 决议 | `backend/app/engine/pending_resolver.py` | `/questions/.../resolve` 编排 seam |
| 存储 | `backend/app/storage/` | `KnowledgeRepo`、`kb_paths`、`kb_media_paths`（聊天上传/生图目录约定） |

## 依赖注入

`backend/app/deps.py` 的 `Container` 持有各运行时模块；构图拆为子图（`deps_index.py` / `deps_memory.py` / `deps_agent.py`），`apply_settings` 经子图 `rebind_llm` 热更新。

- `knowledge_writer` → 注入 `Organizer`、`ToolRegistry`、`MemoryService`、`PreceptsUpgrade`（记忆投影不入 KB 检索）；**须为同一实例**
- `precepts_upgrade: PreceptsUpgrade` → 容器建成后 `sync`（确定性三路）；活《戒律》只经 `knowledge_writer`
- `ImageGen` → 依赖同一 `knowledge_writer` 与 `image_cooldown`（落盘与 failover；见 ADR 2026-08-12）
- `model_cooldown: CooldownStore` → 与 `OpenAILLMClient.cooldown` **须为同一实例**（admin 清冷却 / 选模共用）
- `search_cooldown: CooldownStore` → 与 `WebSearch.cooldown` **须为同一实例**（admin 清冷却 / 搜索 failover 共用；落盘 `.kb/search_cooldown.json`，与 model 冷却隔离）
- `image_cooldown: CooldownStore` → 与 `ImageGen.cooldown` **须为同一实例**（admin 清冷却 / 生图 failover 共用；落盘 `.kb/image_cooldown.json`）
- `models_dev: ModelsDevStore` → 与 enrich/admin 目录查询 **须为同一实例**（`shared_models_dev_store` + `set_active_models_dev_store`）
- `chat_runner: ChatSessionRunner` → 持有 `turn_hub`；`POST /chat` 经 `begin_persisted_turn` + `observe_turn`（生命周期在 hub）
- `derivation_worker` / `memory_worker`（`SessionMemoryObserve`）→ 消费 `ConversationStore.claim_outbox`

`apply_settings()`：`IndexSubgraph.apply_settings`（检索 tunables）+ 各子图 `rebind_llm` + `AgentSubgraph.publish`（同步 Container facade）。

沙箱：`build_sandbox_pool` 由 `AgentSubgraph` / `ToolRegistry` 持有；热更新经 `apply_sandbox_settings(..., pool=)`，不要再假设全局只有一个 `sandbox_runtime`。

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

- **一键拉取（小白）**：单文件启动器 [`deploy/lorechat.sh`](deploy/lorechat.sh) / [`deploy/lorechat.ps1`](deploy/lorechat.ps1)（由 [`scripts/gen-deploy-launchers.py`](scripts/gen-deploy-launchers.py) 生成；运行时在脚本旁写出 compose / 沙箱配置）。独立安装目录数据默认 `./data/`；**在本仓库 `deploy/` 下运行则挂载 `docker/data`**。镜像 tag：`LORECHAT_IMAGE_TAG`（`latest` 或 `0.1.0` 这类，不带 `v`；git tag 仍是 `v0.1.0`）；跟随 master 自动更新：`./lorechat.sh autoupdate on`（Watchtower）；发版流程见 [AGENTS.md](AGENTS.md#二版本发布)
- **源码构建（开发者）**：`docker/docker-compose.yml` + 根 `./lorechat.sh start --chat|--work`（共用 [`scripts/lorechat-compose-lib.sh`](scripts/lorechat-compose-lib.sh)）；`--prebuilt` 改拉 GHCR、数据仍是 `docker/data`
- **可选执行能力**：叠加 sandbox compose；`SANDBOX_ENABLED` / `GET /api/health` → `capabilities.sandbox`。见 [ADR 2026-08-06](docs/adr/2026-08-06-opensandbox-runtime.md)；多角色并行时每角色一把执行沙箱，见 [ADR 2026-09-10](docs/adr/2026-09-10-role-scoped-sandbox.md)。`GET /api/health` 的 `product` 是界面版本号的来源（发行 / 开发）
- OpenSandbox 配置源：`docker/opensandbox/config.toml`（嵌入预构建启动器；开发路径挂载 `docker/opensandbox/`）
- 镜像 pin：`scripts/opensandbox-pins.sh` 由 `gen-deploy-launchers.py` 从 config.toml + sandbox compose 生成；根 `lorechat-compose-lib.sh` source 该文件

## 进一步阅读

- 文档地图：[docs/README.md](docs/README.md)
- 架构决策：[docs/adr/](docs/adr/)
- 产品规格：[docs/product/](docs/product/)

## Language（对话与知识库）

**界面简洁**：面板、浮窗、弹窗头栏只放一个标题。不要小标签叠大标题，也不要在标题下再跟操作说明、重复路径或同义 hint。区块标题下面不要写「控制某某 / 切换某某」这类复述。空位用留白，不要把图标拉变形去填满格子。左栏与中栏（聊天、文档、媒体、聊天通道等浮窗）之间以一根 1px 发丝线分界；不要用投影、渐变或宽色带制造接缝；知识库标题与目录不要贴死，左右不要贴边。不要回到大块空白。拖动缝静息不要画出来，悬停才是同一根 1px 细线；不要用一段画布当拖动槽。滚动条隐藏式，不占位。左栏底栏「主题 / 聊天通道 / 设置」要留在视口里，不能被挤出去，三钮也不要压得太扁。气泡里时间戳、「参考」用留白分开，不要再画一道横线。用户气泡的复制按钮靠时间戳，中间留空隙，不要撑到另一头。助手气泡落款按「时间（时长） 模型名 复制」排成一行，左起，不要把复制甩到另一头。PC 上模型名后跟本轮用量：`入`/`出` 单字微标签 + `K`/`M` 两位小数（不足千则原样），不要用方向箭头表达出入（↓↑语义含糊），也不要写成 `(in:n·out:n)`；悬停或键盘聚焦才露出精确个数。手机不显示用量。折叠处用同一套细线箭头，靠旋转表达开合，不要用 ▸▾▶▼ 字符三角。对话信息流里思考过程、工具卡、参考默认全收起，用户点开才展开；未答征询除外，方便直接点选。思考过程折叠行也标时长，和工具卡同一套数字。执行中的工具卡右侧用时要跟着走，不要停在 0ms。断流重连接到本轮最后一只助手泡上，不要另起一只把思考过程画两遍。手机提问导航用小圆标，不要带字胶囊挡住气泡。手机侧栏是宽抽屉，要显示角色名、目录名和底栏「主题 / 聊天通道 / 设置」文字；不要把桌面最窄图标轨（`app-shell-left--icons`，跟 localStorage 栏宽绑定）套到手机上。群聊助手头像跟名字同一行，正文贴左，不要给头像空出一列。聊天通道和媒体图库头栏不要变宽/变窄按钮。主题弹出菜单要盖过手机侧栏，不要画在抽屉后面。
_Avoid_: `.kb-float-kicker` + 标题 + `.kb-float-crumb` 说明三件套；群成员拼贴用跨行拉伸或 `object-fit: cover` 放大裁切；知识库标题下大块空白；设置分组标题下的同义说明；`.chat-meta` / `.chat-sources` 顶部分隔线；把拖动缝画成一段画布；左栏与聊天/文档/媒体/通道之间留投影或渐变接缝；常驻滚动条；手机提问用带字胶囊 FAB；群角色气泡左侧空一列给头像；通道/媒体头栏 ⟦⟧ 宽窄按钮；底栏三钮压成扁条；主题菜单 z-index 低于手机侧栏；信息流思考/工具/参考默认摊开；执行中工具卡用时停在 0ms；把桌面左栏图标模式套到手机抽屉；手机气泡落款下列 token；落款用量写成 `(in:n·out:n)`；断流重连因缺 `speaker_id` 另起助手泡；观测重放从 seq 0 把快照前的思考/工具再画一遍

**聊天通道浮窗**：入口在左栏底栏「主题 | 聊天通道 | 设置」；点「聊天通道」打开与媒体图库同一套聊天区左缘浮窗（`KbFloatLayer` / `.doc-float-*` + `.kb-float-*`），与记忆/文档互斥同槽。卡片常驻名称 + 类型 badge / 滑动开关 / 可复制 Key 或凭证 / 角色选择 / 思考与工具输出开关（默认关）；脚本吊销后不展示密钥、不可复制。页签（接入说明、会话、日志、吊销或删除）直接画在卡片上，默认只显示页签不展开内容；「共用角色」默认收起。脚本 Key 明文只经 Cookie `GET /api/channel-plugins/instances/{id}/credential` 取出，列表不回传。头栏只保留大标题（如「聊天通道」）和关闭，不要变宽/变窄。
_Avoid_: 把通道再塞回设置页签；用「详情」手风琴包住页签；另做一套底栏气泡/自定义浮层；做成挡住聊天的整页模态；把主题切换只藏进设置；吊销后仍把 Key 前缀当可复制凭证展示；头栏 kicker + 标题 + 说明；通道出站默认带上思考过程或工具结果；把网页 `timeline_state` 原样暴露给脚本 SSE

**模型设置页签**：`ModelSettingsTab` 只装配；有序链 UI 在 `CandidateChainEditor` / `EmbedChainEditor`；draft 解析在 `modelChainDrafts`；能力 lookup 在 `modelCapabilities`；设置 hydrate/serialize 在 `settingsDrafts`（Panel 只接线与副作用）。
_Avoid_: 经 ModelSettingsTab barrel re-export Search/Image 类型或 providerPresets；在页签壳里再堆 ChainEditor；在 SettingsPanel 再堆 parse/put patch 拼装

**模型能力（caps）**：thinking / image / image_wire / video / video_wire / max_videos / max_images / thinking_protocol / effort_options 的权威解析在 `catalog.lookup_capabilities`；设置页经 `GET /api/admin/model-capabilities`（`resolveModelCaps`）。lookup 失败用保守默认。
_Avoid_: 在前端再写一份前缀启发表；用本地 `supportedEfforts` 臆造档位

**聊天附件（图片/视频）**：用户消息仍用 `attachments: string[]`（KB 相对路径）。后端 `media.build_user_content_with_media` 物化为 OpenAI-compatible `image_url` / `video_url`；能力由 `catalog` 声明 `video` / `max_videos` / `max_images`。默认每消息最多 1 个视频；单视频上传上限 50MB（前后端一致）；`video_wire=data` 时文件超过 20MB 且配置了 `public_base_url` 则优先 signed URL。Composer 经 `useChatChainMediaCaps` + `resolveModelCaps` 读取链能力并提示。
_Avoid_: 在 Chat 直接读未 enrich 的 `chat_models` 字段臆断能力；绕过 `kb/import` 大小校验传超大视频

**发送队列**：流式输出时输入框仍可编辑；发送进入按会话隔离的队列（`localStorage`，上限 20）。默认时机 **defer**（当前 turn `done` 后 FIFO/`begin_turn`）；可改为 **inject**（不中断 turn，在 tool 结果回写后、下次 LLM 前插入；无窗口则降级 defer）。「与下一条合并」将同策略相邻项合成一条用户消息。空闲且队列空则直发；停止只中断当前 turn；失败暂停刷队；若回合以未回答的 `ask_user` 征询结束则暂停刷队，待用户作答后再续。前端编排在 `useOutboundOrchestrator`；策略纯函数在 `outboundQueue`。
_Avoid_: 流式中锁死输入；同会话并行多个 running turn；inject 打断当前生成；征询未答时自动刷队；在 `Chat.tsx` 再堆 flush/inject 状态机

**断流重连（观测）**：SSE 断开不取消回合。续接接到本轮最后一只助手泡：未标 `speaker_id` 的乐观壳就是这轮，不要因 `responding_role_id` 另起一泡；已经叠出来的同轮幽灵泡要收掉。Hub `subscribe` 从最新 `timeline_state` 起播，快照前的 delta 不要再给前端 reduce（尚无投影时仍重放增量）。
_Avoid_: `sid` 已知就把无 speaker 的助手当成别人 append；观测重放从 seq 0 把 `think_delta` / `tool_start` 再画到已有时间线上

**征询卡片**：`ask_user` 选项可标 `input`；需要用户写出具体内容时在该选项内展开输入框，一次提交。标签已在邀请自述时同样展开（启发式）。决议经 `inputs` 回传，`continue_prompt` 为「标签：原文」。沙箱确认不提供自述。
_Avoid_: 选完需要自述的选项后再用正文追问同一内容；用课程名/专名黑名单代替 input 契约

**沙箱确认**：高风险 `sandbox_run` 在 trust_mode 关闭时经 `SandboxCommandGate` 建 Pending；用户批准后由 `PendingResolver` 后端代跑（不依赖模型再调工具）。
_Avoid_: 在 Organizer / KB 摄入路径解析 `sandbox_confirm`

**文档托盘（工作托盘）**：用户 Ctrl+单击侧栏**文件或目录**（顶层「技能」除外）加入；项为 `{ path, kind: "document" }`，持久化在 `doc_context`。含义：本轮主要针对这些路径工作（目录=在该目录范围内作业）。编排在 `useComposerPreviewBridge`。
_Avoid_: 附件托盘；用托盘表达 Skill 启用；Ctrl+单击非「技能」根时打开启用窗；在 `App.tsx` 再堆 pin/tray 状态机

**主文档**：托盘内用于默认 `edit_doc` 目标的普通 Markdown 文档。文档元数据用 `write_doc.meta` / `read_doc_meta` / `update_doc_meta`，调用方不感知磁盘定界。
_Avoid_: 在正文伪造 KB 元数据头

**知识库修订**：任意 KB 文件的版本列表与某版正文来自知识库 git（`KnowledgeRepo.list_revisions` / `read_revision`）；HTTP 为 `GET /api/doc/revisions`、`GET /api/doc/revision`。界面 `DocHistoryModal`：文档头栏时钟图标（悬停「修订」）与目录右键「修订」。Markdown 展示去掉库头后的正文；连续相同 blob 合并。窗口固定大小；默认与上一版对照，开关状态不随换版本重置。
_Avoid_: 在 HTTP 里直接跑 git；把冲突标记写进活文件；修订面板只服务《戒律》；在标题下再写路径说明

**官方《戒律》升级**：`PreceptsUpgrade` 用上次同步的官方稿做祖先，与现行正文、新官方稿三路合并（见 [ADR 2026-09-19](docs/adr/2026-09-19-precepts-three-way-upgrade.md)）。无冲突则经 `KnowledgeWriter` 写回并更新祖先；有冲突则活文件不动，打开《戒律》见「戒律更新」：冲突块 + 合并稿，确认后落盘。待确认时知识库「系统」与《戒律》打红点。AI 只填冲突块，不得削弱硬规则；失败则冲突处留当前。`stock.md` 缺失时从该文件 git 历史找回最近一次官方播种稿再三路；仍找不到且正文已本地化时才两路审阅，不覆盖。
_Avoid_: 官方/本库分区；把 `<<<<<<<` 写进现行戒律；启动时静默覆盖已演化的正文；用关键词名单决定保哪一段；绕过 KnowledgeWriter 写《戒律》

**Skill 启用集（catalog）**：跨会话保存在 `.kb/enabled_skills.json`；编排在 `useEnabledSkillsAttach`。**仅** Ctrl+单击顶层「技能」目录（或该目录右键「启用 Skill…」）→ 发现全部包 → 勾选维护默认启用集（首次无启用则默认全选，否则预勾选「候选 ∩ 已启用」）。确认后 `PUT /api/enabled-skills` **整表重写** `roots`。新建或导入 Skill 包（含触发头）时由 `KnowledgeWriter` 默认追加进启用集；改已有 `SKILL.md` 不会把用户关掉的包再打开。删除 Skill 包（或包内 `SKILL.md`）经 `KnowledgeWriter.delete_entry`（界面删除与 Agent `delete_kb` 同一 seam）从启用集去掉该根；目录搬家则 `remap_roots`。每轮注入 name/description（见 `[Skill 目录]`）；命中后再 `read_doc`。启用集**不进**托盘；要对某包改内容，Ctrl+单击该包目录/文件加入托盘即可。Skill 包（含 `SKILL.md`）**必须**落在「技能」目录下（发现 / 启用 / 写入硬约束）；对话 catalog 由 `ChatSessionRunner.resolve_skill_catalog` 装配。对话装配时仍跳过启用集里已删/越界的包（绕过写入 seam 的脏名单），缺触发头的现存包仍 400。
_Avoid_: 挂载即灌入 SKILL.md 全文；子文件夹 Ctrl+单击打开启用窗；把 name/description 写入 `<<<LORE_META`；在 SYSTEM_PROMPT 与 catalog 注入重复写触发契约；在 HTTP 路由内直接编排 `EnabledSkillsStore`；作用域合并双形态 PUT

**Skill 正文头**：每个 `SKILL.md` 正文开头须有 `---` YAML，含非空 `name` 与 `description`（何时使用，语言不限）。缺头时启用/对话返回可读错误，引导用户改文件。KB 文档元数据只用 `<<<LORE_META`；正文 `---` 不作库头解析。文档预览将触发头拆成表格展示，正文交给编辑器；头栏「开发」打开 Markdown 源码后仍编辑原始 YAML；落盘保留原 header 块。
_Avoid_: 无触发头的 Skill 包；用关键词黑名单代替 description；预览里把 YAML 当普通 Markdown 渲染；用 Crepe 序列化结果覆盖掉触发头

**用户生成 Skill 的家规**：何时写包、正文写什么、流程先固化（脚本/模板/显式工作流，模型只做必要判断）、创建时与用户划界、使用中自改进、立规矩走《戒律》第八节；YAML `name`/`description` 在 `write_doc` 契约；本轮用哪个包看 `[Skill 目录]`；主人是谁才进记忆。
_Avoid_: 把作业家规写成主人画像；用 Skill 专名黑名单代替「助手怎么做事 ≠ 主人是谁」；在 SYSTEM_PROMPT 或每个 SKILL.md 复述落库/检索家规；在《戒律》堆 YAML 触发头 schema；把整包写成只靠模型临场发挥的提示词；在《戒律》点名必须有某个脚本文件；把本轮流水账写进 SKILL.md；一次失败重写整包；使用中改进写进主人画像

**知识库树 viewport UI**：侧栏目录的展开态与滚动位置（hydrate / 临时露出 / 恢复 / 落盘）收在 `useKbTreeViewportUi`；`FileTree` 只渲染受控展开；存储细节在 `kbTreeUiStorage`。
_Avoid_: 用 `onExpandReady` 跨组件握手；在 `FileTree` / `Sidebar` 再拆一套展开或滚动状态机

**托盘项类型（kind）**：仅 `document`。历史消息里的 `skill_root` 读出时一律当作 document 展示；Skill 启用与激活不经托盘。
_Avoid_: 再引入托盘 Skill 专用 kind / 标签；用托盘驱动 catalog

**多 Skill 并存**：同一启用集可含多个包；catalog 分段列出；与用户消息冲突以用户消息为准；Skill 之间冲突则合并取交集或向用户澄清。
_Avoid_: 每轮仅允许一个 Skill（除非产品另行限制）
