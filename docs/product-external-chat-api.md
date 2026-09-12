# 对外聊天 API（草案）

> 状态：**草案**（2026-09-12）。尚未落地代码。本文是实现对照规格；采纳后另写 ADR，不改写本文已拍板的决策段。
>
> 配套现状：[CONTEXT.md](../CONTEXT.md) 聊天持久化、[product-multi-role.md](product-multi-role.md) 角色时间线、[ADR 2026-09-10 timeline](adr/2026-09-10-role-timeline.md)。

## 0. 已采用的默认（沟通未回时的拍板）

主人原话要解决三件事：接口形态、会话是新建还是接续、API 历史怎么在产品里展示。下列默认按「自己的脚本/自动化为主，Key 也可以发给可信外部」来写；若之后改口径，只改本节与标了「可改」的段落。

| 问题 | 默认 |
|------|------|
| 谁来调用 | 主人签发 API Key。自己的脚本、n8n、另一个 bot、把 Key 交给可信第三方都可以。不是多租户 OAuth，也不是把网页 Cookie 接口裸开。 |
| 会话 | **两种都支持**。不传 ID 则每次新建并落库；传 `conversation_id` 或调用方 `thread_id` 则接续。 |
| 历史展示 | 挂到 Key 绑定（或请求指定）的角色时间线，带 **API** 标记，可筛「全部 / 仅网页 / 仅 API」。**不**虚构「开放接口」角色。 |
| 会不会抢走正在聊的 tip | **不会**。`origin=api` 的段不参与 `ensure-active` / 连续窗口 / 「新话题」。 |
| 默认能力 | 对话 + 指定 Skill + 读知识库。写库 / 沙箱 / 联网须 Key 显式授权。 |
| 首期响应 | 同步 JSON（脚本好接）。超时返回进行中，可轮询；SSE 与 OpenAI 兼容形态放后续。 |

## 1. 要解决的问题

Lore Chat 已经是带角色、Skill、知识库、工具循环的聊天机器人。网页主入口是 Cookie 登录后的 `POST /api/chat`（SSE，会话挂在角色时间线上）。

主人希望**对外**开一个聊天接口：例如做好一个 Skill，外部系统按 HTTP 调用，拿到工作回复。现有网页契约不适合外开：

- 鉴权只有 `lorechat_session` Cookie，脚本和第三方接不了。
- `/api/chat` 绑定托盘、观测通道、内部 timeline 事件，契约会随 UI 漂移。
- 无 `conversation_id` 时走 `stream_ephemeral`，不落库，历史无法展示。
- Skill 是全局启用集，无法按调用方收窄到「只跑这一个 Skill」。

## 2. 目标与非目标

### 目标

1. 主人在设置里签发/吊销 API Key，外部用 `Authorization: Bearer` 调用。
2. 一次调用就能跑指定 Skill（及该角色的人设、记忆、知识库检索），返回助手回复。
3. 调用方可选择「每次新会话」或「接续同一段上下文」。
4. API 产生的会话在产品里可见、可搜、可区分来源。
5. 外部契约稳定、短；内部 Agent 执行仍走现有 `TurnExecutionHub` / `ChatSessionRunner`，HTTP 层不解析 Agent SSE。

### 非目标（明确不做）

- 多租户账号、OAuth 应用市场、按调用方计费。
- 把 `/api/chat`、`/api/conversations`、管理/设置/知识库树原样对外。
- API 调用走 ephemeral（不落库）。
- 调用方在请求里上传整份 `SKILL.md`（Skill 必须已在「技能」目录并被 Key 允许）。
- 首期做 OpenAI `/v1/chat/completions` 兼容（P2 再加适配层，不替代本契约）。
- 虚拟「开放接口」角色，或把 API 会话与网页会话物理拆成另一套库。

## 3. 产品模型

```
外部调用方 --Bearer Key--> /api/v1/chat
                              │
                              ├─ 解析 Key：角色、Skill 白名单、能力范围
                              ├─ 解析会话：新建 / 续 conversation_id / 续 thread_id
                              ├─ ChatSessionRunner.begin_persisted_turn
                              └─ 同步等回合结束（或超时返回 running）
                                      │
网页主人 <── 同一 ConversationStore ──┘
         角色时间线看到带 API 标记的段；tip 算法忽略这些段
```

一条对外聊天 = 一条普通 `conversation` 行，额外带上来源字段。角色、记忆抽取、知识库仍是全局那一套；**来源只影响鉴权范围、tip 算法和 UI 标记**。

Key 是能力凭证，不是第二个主人账号。Key 只能读写**它自己创建的** API 会话，不能列出或续写主人的网页会话。

## 4. 会话模型

这是本需求的核心。三种入口，语义正交。

### 4.1 每次新绘画（默认）

请求不带 `conversation_id`、不带 `thread_id`：

1. `conversations.create(title=…, role_id=…)`，写入 `origin=api` 等来源字段。
2. 本轮作为该段第一条用户消息，跑 Agent。
3. 响应带回 `conversation_id`。调用方若要接着聊，下次带上即可。

适合：一次 Skill 作业、一条工单处理、无状态 webhook。

### 4.2 按 Lore 会话 ID 接续

请求带 `conversation_id`：

- 会话必须存在、`origin=api`、且 `api_key_id` 等于当前 Key。
- `role_id` 若传入必须与会话一致，否则 409 `role_mismatch`（与现网 `/api/chat` 相同）。
- 同一会话仍遵守「同时只有一个 running turn」；冲突 409 `turn_in_progress`。

适合：调用方愿意保存我们返回的 ID，做多轮工作流或角色向聊天。

### 4.3 按调用方 thread_id 接续

请求带 `thread_id`（调用方自己的稳定字符串，例如 `crm:ticket:1234`、`slack:Cxxx:txxx`）：

- 在 `(api_key_id, thread_id)` 上查找映射。
- 已有则续该 `conversation_id`。
- 没有则新建会话并写入映射。
- `thread_id` 与 `conversation_id` 同时传入时：以 `conversation_id` 为准，并校验映射一致，否则 409 `thread_mismatch`。

适合：外部系统已有线程概念，不想管理 Lore 的 ID。这是「有点像角色聊天、固定一段上下文」的主要用法。

### 4.4 不采用的做法

- **每次都 ephemeral**：历史无法展示，也没法接续。
- **一个 Key 永远只有一条会话**：多个工单会串上下文。
- **网页 tip 被 API 续写**：外部一调用，主人正在打的字就被接走。API 会话与 tip 隔离，见 §7.2。
- **跨 Key 共享 conversation_id**：Key 泄露不应看到别人（另一把 Key）的线程。

## 5. 鉴权与 Key

### 5.1 形态

```
Authorization: Bearer lc_live_<secret>
```

- 明文只在创建时显示一次。
- 落盘只存 SHA-256（或等价单向哈希）与 `key_prefix`（前 8 位，便于辨认）。
- 存储：`{kb}/.kb/api_keys.json`（与分享链接、启用 Skill 一样走 KB 侧配置，不进 git 知识正文）。
- 设置页新页签「开放接口」：创建、命名、吊销、看上次使用时间。不把完整 Key 再读出来。

### 5.2 Key 字段

| 字段 | 含义 |
|------|------|
| `id` | 稳定内部 id（`api_key_id`） |
| `name` | 主人起的名字，时间线徽章上显示 |
| `role_id` | 默认角色；请求可覆盖为同一把 Key 允许的角色（首期只允许这一个） |
| `skills` | 允许的 Skill 根路径；空 = 使用当前全局启用集与其交集（见 §6） |
| `capabilities` | 默认 `["chat"]`；可选 `kb_read`（默认开）、`kb_write`、`sandbox`、`web` |
| `exp` | 可选过期 |
| `revoked` | 吊销后立即 401 |

中间件：仅 `/api/v1/*` 接受 Bearer。现有 Cookie 路由不变。一把 Key **不能**调用 `/api/settings`、`/api/kb/*`、管理接口。

`GET /api/health` 仍公开，不带 Key。

### 5.3 CORS 与入口

依赖已有 `public_base_url`。设置里可配 `api_cors_origins`（默认空 = 非浏览器脚本，不开放任意网站跨域）。浏览器插件/网页调用须主人显式加源。

## 6. Skill

「做好一个 Skill 再对外调用」是本需求的主场景。

- Skill 包仍必须落在「技能」目录，有合格 YAML 头（现网硬约束不变）。
- 每轮 catalog = `（Key.skills 若非空，否则全局启用集） ∩ 请求.skills（若传入）`。
- 交集为空则 400，而不是悄悄跑成「无 Skill 的通用聊天」。
- 调用方**不**传 Skill 正文；命中后仍由 Agent `read_doc` 拉取，与网页相同。
- 禁止按 Skill 名做关键词黑名单；收窄只通过 Key 白名单与当次 `skills`。

请求示例：只跑一个包时传 `"skills": ["技能/周报助手"]`。

## 7. 历史如何展示

### 7.1 时间线

API 会话是该 `role_id` 下的普通段，出现在 `GET /api/roles/{id}/timeline`：

- 段上有徽章 **API**，副文案为 Key 的 `name`（没有则「开放接口」）。
- 标题：请求 `title` → 否则首条用户消息截断（沿用 `title_from_text`）。
- 段间分隔与现网一致；不把多段合并成一行。
- 工作区搜索（会话 FTS/向量）包含 API 段，结果可带来源以免和网页聊天分不清。

中栏筛选（角色时间线顶或搜索旁）：**全部 / 仅网页 / 仅 API**。默认「全部」，避免主人不知道外部刚跑过什么。

### 7.2 绝不能抢走 tip（硬约束）

现网 `ensure_active_conversation` / `find_active_conversation_id` / `open_new_topic` 按「该角色最新会话 + 连续窗口」决定可写 tip。若 API 新建或更新一段，`updated_at` 会变成最新，主人再打开角色就会落到 API 段上，或把网页连续窗口打断。

因此：

1. `conversations` 增加 `origin`（`web` \| `api`，缺省 `web`）。
2. tip 算法、空段复用、「新话题」、角色「最近活动」若表示「主人上次亲口聊」，**只看 `origin=web`**。
3. API 段出现在时间线里，但是只读段（与今天的历史段一样）。
4. 主人要在网页里接着某段 API 聊：P1 提供「继续此段」（显式把该段设为当前 tip；`origin` 仍为 `api`）。首期不做自动提升。
5. Agent 若 `ask_user` 或沙箱确认：走现有 Pending / `/api/questions`，主人在网页待办里回答。同时 API 响应 `status=needs_input`（§9）。

角色列表副标题：默认仍优先网页最近回复；若该角色只有 API 活动，可以显示「API · …」以免看起来像没聊过。实现时二选一写进 ADR，不在 tip 算法里混用。

### 7.3 不采用单独入口的理由

单独做「开放接口」角色或独立页面，会让 Skill 的人格和主人选的会话角色脱节，也会再维护一套列表。来源标记 + 筛选 + tip 隔离已经能把「日常聊天」和「外部作业」分开。

若日后 API 量极大、时间线被刷屏，再加「默认隐藏 API 段、筛选才显示」，不改数据模型。

## 8. 对外 HTTP 契约

前缀：`/api/v1`。DTO 用稳定英文字段。错误体：`{"code": "…", "message": "…"}`。

### 8.1 `POST /api/v1/chat`

```json
{
  "message": "用周报助手把下面材料整理成周报：…",
  "conversation_id": null,
  "thread_id": "weekly:2026-W37",
  "role_id": null,
  "skills": ["技能/周报助手"],
  "title": "2026-W37 周报",
  "stream": false,
  "wait": true,
  "timeout_sec": 120
}
```

| 字段 | 说明 |
|------|------|
| `message` | 必填，用户文本。首期不做附件/托盘（外部把材料放进 message 或先由主人写入 KB）。 |
| `conversation_id` | 续指定会话，见 §4.2。 |
| `thread_id` | 调用方线程键，见 §4.3。 |
| `role_id` | 可选；缺省用 Key 绑定角色。 |
| `skills` | 可选，当次再收窄。 |
| `title` | 仅新建会话时采用。 |
| `stream` | 默认 `false`。`true` 为 P1 精简 SSE。 |
| `wait` | 默认 `true`：等回合结束或超时。 |
| `timeout_sec` | 默认 120，上限 600。超时不取消回合。 |

同步完成：

```json
{
  "conversation_id": "a1b2c3d4e5f6",
  "thread_id": "weekly:2026-W37",
  "turn_id": "…",
  "status": "completed",
  "message": {
    "id": "…",
    "role": "assistant",
    "content": "本周纪要：…"
  },
  "usage": { "input_tokens": 0, "output_tokens": 0 }
}
```

`status`：`completed` \| `running` \| `needs_input` \| `failed` \| `stopped`。

超时且 `wait=true`：HTTP 202，body 仍是同一形状，`status=running`，`message` 为已有部分或 `null`。调用方 `GET /api/v1/conversations/{id}` 或 `GET .../turns/{turn_id}`。

`needs_input`：`message.content` 可为截止提问前的文本；另给 `pending`：

```json
{
  "pending": {
    "id": "…",
    "kind": "ask_user",
    "prompt": "周报里要不要写未完成项？",
    "choices": ["要", "不要"]
  }
}
```

调用方 `POST /api/v1/questions/{id}/resolve`（P1）；首期也可由主人在网页点选，调用方轮询会话直到 `completed`。

### 8.2 只读与控制

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/conversations` | 仅本 Key 的会话；可选 `thread_id` |
| GET | `/api/v1/conversations/{id}` | 消息列表（可 `tail`） |
| GET | `/api/v1/conversations/{id}/turns/{turn_id}` | 回合状态 |
| POST | `/api/v1/conversations/{id}/stop` | 停当前回合 |
| GET | `/api/v1/skills` | 本 Key 当前可用 catalog（name/description/root） |
| POST | `/api/v1/questions/{id}/resolve` | P1：回答征询 |

列出/读取越权（别人的网页会话、另一把 Key 的会话）→ 404，不泄露存在性。

### 8.3 流式（P1）

`stream=true` 时 `text/event-stream`，**公开事件只有**：

- `delta`：`{ "text": "…" }`
- `status`：`{ "status": "running|needs_input|completed|failed" }`
- `done`：与同步响应同形的最终对象
- `error`：`{ "code", "message" }`

不对外暴露内部 `timeline_state` / tool 卡片 / keepalive 细节。实现上仍 `observe_turn`，在 **PublicChat 服务**里投影，路由只挂 `StreamingResponse`。

### 8.4 调用示例

```bash
curl -sS "$LORECHAT/api/v1/chat" \
  -H "Authorization: Bearer lc_live_…" \
  -H "Content-Type: application/json" \
  -d '{"message":"把这段会议记录写成纪要：…","skills":["技能/会议纪要"]}'
```

接续同一工单：

```bash
curl -sS "$LORECHAT/api/v1/chat" \
  -H "Authorization: Bearer lc_live_…" \
  -H "Content-Type: application/json" \
  -d '{"thread_id":"ticket:8848","message":"补充：客户改约到周五。"}'
```

## 9. 能力、工具与人机确认

Agent 工具循环与网页同一套。Key 的 `capabilities` 在组 catalog / 跑工具前裁剪：

| 能力 | 缺省 | 没有时 |
|------|------|--------|
| `chat` | 有 | Key 无效 |
| `kb_read` | 有 | 不注入检索、禁用 `read_doc` / `search_kb`（Skill 正文仍允许按包读取，否则 Skill 无法工作） |
| `kb_write` | 无 | 禁用 `write_doc` / 归档 / 导入 |
| `sandbox` | 无 | 禁用沙箱工具 |
| `web` | 无 | `web_enabled` 强制 false |

`kb_read` 与「读 Skill 包」要分开：即使关掉通用 KB 检索，仍须能 `read_doc` 已允许的 Skill 根。实现时在工具层按路径白名单，而不是提示词里写个案。

沙箱在网页有 `SandboxCommandGate`。API 默认**不**自动批准。未授 `sandbox` 则工具不可见；授了但仍触发确认时 → `needs_input` + 网页待办。P2 才考虑 Key 级 `auto_approve_sandbox`（默认关，文案写清风险）。

## 10. 记忆

API 会话走同一套 outbox / `SessionMemoryObserve`。关段、空闲抽取规则不变。

抽取提示词仍是关于主人 / 耐久性 / 语境保全三道门槛：外部工单、Skill 作业步骤、调用方业务数据**默认不是主人画像**。不在本文另写抽取黑名单。

API 段不自动当 tip，因此「关段抽取」不会因为 API 刷屏而把主人网页 tip 误关；API 段自身的空闲抽取仍可跑。

## 11. 存储与实现 seam

### 11.1 会话列（`ALTER`，缺省兼容旧行）

`conversations` 增加：

- `origin TEXT NOT NULL DEFAULT 'web'`
- `api_key_id TEXT`
- `external_thread_id TEXT`
- 索引：`(origin, role_id, updated_at)`；`(api_key_id, updated_at)`

映射表（可放 `conversations.db` 或 `{kb}/.kb/api_threads.json`；推荐 SQLite）：

- `api_key_id, thread_id, conversation_id`，主键 `(api_key_id, thread_id)`，`conversation_id` 唯一。

### 11.2 模块边界

| 层 | 职责 |
|----|------|
| `AuthMiddleware` | `/api/v1/*` 校验 Bearer，把 `api_key` 挂到 request；其它路由仍只认 Cookie |
| HTTP `v1_routes` | DTO、状态码、StreamingResponse；**不**解析 Agent SSE |
| `PublicChatService` | 解析会话/线程、裁剪 Skill/工具、`begin_persisted_turn`、等到 `finalize`、投影公开响应 |
| `ChatSessionRunner` / `TurnExecutionHub` | 不分来源；多一个 origin/catalog 入参即可 |
| `ConversationStore` | tip 查询加 `origin='web'`；create 接受来源字段 |
| 设置 UI | Key CRUD；时间线徽章与筛选 |

禁止：在 `chat_routes.py` 里加 `if api_key`；在路由里 `async for` 解析内部 SSE 拼最终回复；为 API 再写一套 Agent 循环。

`create` 与 tip 复用必须分开：API **永远** `create` 新行或续已有 API 行，不调用 `ensure_active_conversation`。

## 12. 前端

1. 设置 → **开放接口**：创建 Key（角色、Skill 多选、能力勾选）、复制一次、列表、吊销；展示 `POST {public_base_url}/api/v1/chat` 示例。
2. 角色时间线段分隔处：`origin=api` 显示 API 徽章 + Key 名。
3. 筛选：全部 / 仅网页 / 仅 API。
4. 待办（已有 questions）继续承接 API 回合的征询，无需新入口。
5. P1：「继续此段」出现在 API 段操作里。

不在 `Chat.tsx` 再堆一套来源状态机；筛选与徽章跟时间线数据走。

## 13. 分期

**P0（可对外真用）**

- Key 签发/吊销 + Bearer
- `POST /api/v1/chat` 同步（新建或 `conversation_id` 续）+ 超时 202
- `GET` 会话/回合、`POST` stop
- `GET /api/v1/skills`
- 落库 `origin=api`；tip 算法排除 API 段
- 时间线徽章 + 筛选
- 能力默认：chat + 读 KB/Skill；写库/沙箱/联网默认关

**P1**

- `thread_id` 映射
- `stream=true` 精简 SSE
- `POST /api/v1/questions/{id}/resolve`
- 网页「继续此段」
- 简单每 Key 速率限制

**P2**

- OpenAI 兼容适配（`messages[]` → 本契约；方便现成客户端）
- Key 用量（对接现有 usage）
- CORS UI、Key 过期、`auto_approve_sandbox`
- 附件（先导入 KB 再带路径，或受限上传）

## 14. 验收意图

不写孤例补丁，只验根因同类：

1. **无 Key / 坏 Key** → 401；Cookie 登录不能当 v1 凭证，Bearer 不能当网页凭证。
2. **不传会话 ID** → 新段、`origin=api`、时间线可见、主人 tip 不变。
3. **再带返回的 conversation_id** → 同一段接续；Agent history 含上一轮。
4. **另一把 Key 带该 conversation_id** → 404。
5. **指定 skills** → catalog 只有交集；交集空 → 400。
6. **未授 sandbox 的 Key** → 工具不可见，不会冒出沙箱确认。
7. **网页连续窗口内**外部连打多轮 API → 主人再进该角色，tip 仍是原来的网页段。
8. **筛选「仅网页」** → API 段消失；「仅 API」反之。

## 15. 明确不采用

- 复用 `/api/chat` 加一个 header 冒充对外开放
- API 默认 ephemeral 或默认自动批准沙箱
- 用关键词禁止某些 Skill 名
- 为 API 单独做记忆抽取提示词
- 时间线物理合并 API 与网页消息
- 首期只做 OpenAI 兼容、不做自己的稳定契约

## 16. 若之后改口径

| 若主人改口 | 怎么改（不动 P0 骨架） |
|------------|------------------------|
| 只要自己用、不要给别人 Key | 仍然用 Key；只是不把 Key 发出去。契约不用变。 |
| 和日常聊天完全分开 | 加筛选默认「仅网页」+ 设置里「API 会话列表」；或后期专用角色。数据仍是 `origin=api`。 |
| 外部默认可写库、跑沙箱 | 创建 Key 时默认勾选对应 capabilities，不要去掉授权模型。 |
| 必须对接现成 OpenAI 客户端 | P2 适配层，映射到同一 `PublicChatService`。 |
