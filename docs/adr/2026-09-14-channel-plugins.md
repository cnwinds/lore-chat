# ADR 2026-09-14：聊天通道插件（Channel Plugin）

## 状态

**已确认 / P1 已落地**（2026-09-14）。产品口径已拍板，见 [product-channel-plugins.md](../product-channel-plugins.md) §12。P0 脚本通道与 P1 飞书长连接、按实例日志/用量已落地。本篇是架构摘要，不替代 product 文。

## 背景

已落地对外脚本 API：人设可共享；每把 Key 一个 hidden 工作角色；`POST /api/v1/chat` 经 `OpenApiService.complete_chat` → `begin_persisted_turn`（`mode=api`，`origin=api`）。设置页「开放接口」管密钥、调用说明、说话方式。

主人希望：开放接口做成类似插件；微信 / 钉钉 / 飞书 / Slack 等外部对接都走同一方式；每份可配不同参数；启用后能在外部聊天。

补充口径：**统一叫「聊天通道插件」**。不要泛泛叫「插件」。不要把脚本和 IM 当成两套无关产品。平台差异只是适配层；人设、查看会话、启停/状态、会话映射等为共有能力。

风险：为每家 IM 各写一套对话引擎；脚本与 IM 两套设置/两套人设；或把外部群接到角色群；或在 webhook 里编排 Agent（违反 [CONTEXT.md](../../CONTEXT.md) 与 [ADR 2026-08-04](2026-08-04-engine-module-seams.md)）。

## 决策

### 1. 一个公共模型，类型只做适配

产品对象是 **聊天通道插件**。现有 API Key 是第一种类型（`script_api` / HTTP），与飞书等**同级列表**。页签 **「聊天通道」**，不要「开放接口」主名或副名。

共有：`persona_id`、hidden `role_id`、启停与状态、外部线程 → `conversation_id`、按实例只读时间线、`mode=api` 回合。日志/用量按通道实例在 **P1** 做；P0 脚本沿用「上次调用」。

特有：config/secret schema、ingress（Bearer / webhook / 长连接）、同步 wait vs 先 ACK 再 reply。

适配器只做厂商协议。回合仍走 `TurnExecutionHub` / `ChatSessionRunner`。HTTP **不**解析 Agent SSE。

### 2. 人设只绑 persona（方案 A）

通道选的是 **说话方式（persona）**，不是左栏工作角色。从左栏创建时只**复制**名称/头像/提示词。不跟随左栏 `system_prompt`。直接挂左栏 `role_id` **否决**。

### 3. 每通道实例一个 hidden 工作角色 + IM 入站排队

与「每把 Key 一个角色」同构。不按外部线程开角色。外部 `chat_id` / `thread` / `openid` 经查找表映射到 `conversation_id`。

私聊：每个外部用户一段会话。群/频道：仅被 @ 或被引用才开回合；无 @ 裸消息忽略；有 thread 能力则回复开成 thread。

### 4. IM 入站先 ACK，后台跑回合

Webhook 在厂商时限内 200。同角色忙：脚本仍 HTTP 409；其它类型 ACK 后入队，不对平台 409。长回合**不要**先发「还在处理」。

webhook 缺 `public_base_url`：**允许保存**；启用校验失败 → `status=error`。长连接与 `script_api` 不依赖公网。

### 5. 全部聊天通道默认 `mode=api`

只读 KB + Skill + 沙箱；不写库、不回写、不改角色/例行、不派工。`origin`：`api` 留给脚本；IM 用类型名。左栏与记忆调度排除全部通道 origin。**P1 非脚本通道不抽记忆。P1 允许非脚本通道用沙箱**；群聊默认关沙箱直到有发送者白名单。

外部群 ≠ lore-chat 角色群。

### 6. 模块位置

`backend/app/engine/channel_plugins/`：`ChannelPluginRegistry`、`ChannelAdapter`、实例存储、`ChannelTurnService`。公开入站只验签 + adapter。出站只经 adapter。

脚本 token 继续哈希；IM secret 对齐 `settings.json` 脱敏。P0 不做单独信封加密。

### 7. 分期

P0 公共模型 + Key 投影为第一种通道 + 同级列表 UI，行为不变。**P1 = 飞书长连接** + 按实例日志/用量。P2 其余类型、群/频道（按 §3 口径）、富媒体。

## 后果

- 设置页「开放接口」演进为「聊天通道」；脚本与 IM 同一卡片结构。
- `sandbox_max_api_roles` 计入所有 hidden 通道角色。
- 飞书长连接 task 挂在 `Container` 生命周期。
- 需公共 `channel_threads` 与入站去重；`origin != api` 改为通道 origin 集合。

## 明确不采用

- 泛插件平台 / 商店 / 侧载 / 多租户 OAuth
- 脚本与 IM 两套人设/会话/设置页
- 「开放接口」作页签主名或副名
- 个微非官方协议
- 多实例共用一个 `role_id`，或通道借用左栏角色沙箱
- 按外部线程默认再开多把沙箱
- webhook 内同步跑完整 Agent 直到超时
- 长回合预告「还在处理」
- 把通道会话画进左栏 tip；P1 对非脚本通道抽画像
- 因缺公网根而禁止保存 webhook 配置
