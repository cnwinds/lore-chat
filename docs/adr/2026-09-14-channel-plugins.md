# ADR 2026-09-14：通道插件（外部协议适配）

## 状态

**提案 / 待确认**（2026-09-14）。不是已采纳。产品展开见 [product-channel-plugins.md](../product-channel-plugins.md)。确认前不得当实现依据去改业务代码。

## 背景

已落地对外脚本 API：人设可共享；每把 Key 一个 hidden 工作角色；`POST /api/v1/chat` 经 `OpenApiService.complete_chat` → `begin_persisted_turn`（`mode=api`，`origin=api`）。设置页「开放接口」管密钥、调用说明、说话方式。

主人希望：开放接口做成插件；微信 / 钉钉 / 飞书 / Slack 等外部对接都走插件；每实例一套参数；启用后能在外部聊天。

风险：为每家 IM 各写一套对话引擎；或把外部群接到角色群（rooms）；或在 webhook 路由里编排 Agent（违反 [CONTEXT.md](../../CONTEXT.md) 与 [ADR 2026-08-04](2026-08-04-engine-module-seams.md)）。

## 决策（提案）

### 1. 插件是协议适配器，不是第二套 Agent

插件只做：厂商鉴权、ingress（Bearer / webhook / 长连接）、配置、入站归一化、出站回复。回合仍走 `TurnExecutionHub` / `ChatSessionRunner`。HTTP **不**解析 Agent SSE、不自建工具循环。

### 2. 四层模型 + 会话键

| 层 | 含义 |
|----|------|
| Plugin Type | 内置代码（`script_api`、`feishu`、…），声明 schema 与 ingress |
| Plugin Instance | 用户的一份配置（参数、启用、`persona_id`） |
| Hidden work role | **默认每实例一个**；沙箱与 running turn 仍按角色锁 |
| Persona | 可跨实例共享；活引用 |

外部 `chat_id` / `thread` / `openid` 经查找表映射到 `conversation_id`，不把外部 id 当内部主键。

脚本 API **就是**类型 `script_api`，与 IM 同一设置列表；v1 契约与已确认 [product-external-chat-api.md](../product-external-chat-api.md) 不变。

### 3. IM 入站先 ACK，后台跑回合

Slack / 飞书等不能同步等 120s。Webhook 在厂商时限内 200；长连接读循环不阻塞。`event_id` 幂等。同角色忙：HTTP **不**对 IM 回 409（脚本 Key 仍 409）；事件入队。

### 4. 全部通道默认 `mode=api`

只读 KB + Skill + 沙箱；不写库、不回写、不改角色/例行、不派工。`origin`：`api` 留给脚本；IM 用 `feishu` / `slack` / …。左栏与记忆调度排除全部外部 origin（现网只排除 `api`，采纳后要改）。

外部群 ≠ lore-chat 角色群。IM 用户不是内部 Actor。

### 5. 模块位置

`backend/app/engine/plugins/`：`PluginRegistry`、`ChannelAdapter`、实例存储、`ChannelTurnService`（验实例 → 映射会话 → `begin_persisted_turn`）。公开入站路由只验签 + 调用 adapter。出站只经 adapter。

密钥：脚本 token 继续哈希；IM secret 对齐 `settings.json` 脱敏与「空值不覆盖」，P0 不做单独信封加密。

### 6. 分期

P0 框架 + Key 投影为 `script_api` + 设置骨架，行为不变。P1 一个免公网 IM（建议飞书长连接，或主人指定 Slack Socket Mode）。P2 其它 IM、群、富媒体。

## 后果（若采纳）

- 设置页「开放接口」演进为插件列表；说话方式折叠保留。
- `sandbox_max_api_roles` 计入所有 hidden 外部角色（Key + IM）。
- 飞书/Slack 长连接在 `Container` 生命周期内常驻 task。
- 需 `channel_threads` 与入站去重；需把 `origin != api` 的过滤改成外部 origin 集合。

## 明确不采用

- 插件商店 / 侧载 / 多租户 OAuth
- 个微非官方协议
- 多实例共用一个 `role_id`，或为 IM 绕过角色沙箱锁去「借用」左栏
- 在请求或事件里指定左栏角色
- webhook 内同步跑完整 Agent 直到超时
- 把通道会话画进左栏 tip
