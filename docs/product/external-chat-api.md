# 对外聊天 API

> 状态：**已落地**（脚本通道 P0）。人设可共享；**每把 API Key = 一个独立隐藏角色**（独立沙箱、独立会话）。P1 精简 SSE（`stream: true`）已落地；其余 P1/P2（`thread_id`、独立人设、OpenAI 兼容网关等）仍后置。
>
> 已被 [聊天通道插件](channel-plugins.md) 作为第一种通道（`script_api`）包含。本文仍是脚本 Key / `POST /api/v1/chat` 的权威口径；P0 **不改**这些行为。设置入口现为「聊天通道」。
>
> 配套：[CONTEXT.md](../../CONTEXT.md)、[multi-role.md](multi-role.md)、[ADR 2026-09-10 timeline](../adr/2026-09-10-role-timeline.md)、[ADR 2026-09-10 sandbox](../adr/2026-09-10-role-scoped-sandbox.md)。

## 0. 一句话

脚本用 Key 调 `POST /api/v1/chat`。创建 Key 时选一套**人设**（可以和别的 Key 选同一套，也可以各选各的）。系统为**这把 Key 新建一个隐藏角色**去干活：同一套角色逻辑（人设注入、时间线、沙箱 slot），但不进左栏。多把 Key 同时调，互不堵；看日志也是按 Key 分开。

## 1. 为什么不能「多把 Key 共用一个角色」

现网一个 `role_id` 绑死三件事：人设、会话时间线、**一把沙箱**。同一角色上：

- `sandbox_run` / stop / interrupt 打在同一容器、同一张盘；
- 同会话还有「同时一个 running turn」。

所以多把 Key 若都挂 `__api__`，并发会互相堵住、日志也会搅在一条时间线上。这和「自己可能开多把 Key、甚至以后一人一把」冲突。

拆成两层就顺了：

| 层 | 是什么 | 能否共享 |
|----|--------|----------|
| **人设** | 名称、头像、提示词（你在设置里配的「角色样子」） | 能。多把 Key 可以选同一套 |
| **工作角色** | `roles` 表里一行隐藏角色：自己的 `role_id`、沙箱、会话 | **不能。一把 Key 恰好一个** |

「使用同一个角色」在产品语言里 = **选用同一套人设**。底下仍是多个角色在工作，只是提示词同一份。

## 2. 已拍板（其余口径）

| 点 | 决定 |
|----|------|
| 谁调用 | 自己的脚本/自动化。低并发。不做多租户、OAuth、全局限流。 |
| 展示 | 不进左栏，不进日常角色时间线。入口在左栏底栏「聊天通道」。 |
| KB / Skill | 可读、可跑 Skill；不能改 KB、不能改 Skill、不能沙箱回写。 |
| 沙箱 | 能跑。每个工作角色一把容器/卷，与左栏角色互不 interrupt。 |
| 会话 | 默认每次调用新建一段；可带该 Key 自己的 `conversation_id` 多轮。 |
| 响应 | 默认同步 JSON；超时 202。可选 `stream: true` 精简 SSE（断开不取消执行） |

## 3. 数据怎么落

创建一把 Key 时系统做三件事：

1. 写入 Key（哈希、名称、`persona_id`、`role_id`）。
2. `roles.create`：`visibility=hidden`，`id` 如 `api_<key短id>`，`onboarding_status=completed`，不可当默认、不进左栏、不可从左栏删。
3. 工作角色挂上 `persona_id`。Agent 注入时**读人设的当前提示词**（活引用，不是创建时拷死一份）。改人设，所有选用它的 Key 下一轮生效。某一把 Key 要走样：在 Key 上「改为独立人设」（复制出一份新 persona，只属于它）。

会话：`role_id = 该 Key 的工作角色`，`origin=api`，`api_key_id = 这把 Key`。

沙箱：`RoleSandboxPool.get(该工作角色 id)`。现网「永不借用其它角色」直接成立，不必再发明第三种 slot。

左栏 `GET /api/roles` 只返回 `visibility=sidebar`。`ensure_active` / tip / 最近活动只看 `origin=web`。

吊销 Key：不能再调 v1，**历史和工作角色留下**，设置里仍能看日志。删除 Key（P1）：可选毁掉该角色沙箱卷。

## 4. 界面（密钥优先，人设收进创建）

设置 → **开放接口**。首页只做一件事：**管密钥**。底层仍是「人设可共享 / 每 Key 一个隐藏角色」，但不要把这套分层摊成两张表单。

### 4.1 首页

- 一行标题 + 一句说明 + **创建密钥**
- 空态：还没有密钥，主按钮就是创建
- 列表每张卡：密钥名、说话方式徽章、前缀、上次调用、**查看会话**、吊销
- 「调用方式」「说话方式」收进折叠，不占首屏

### 4.2 创建密钥

单独一页，默认只要名称。说话方式一个下拉：

- **默认（和密钥同名）**：后端按密钥名建一套人设
- 已有人设：多把 Key 共用提示词
- 新建一套 / 从左栏角色复制（只拷名称/头像/提示词，**不**绑那个角色的沙箱和聊天）

创建后回到首页，明文密钥只显示一次（复制密钥 / 复制 curl）。

### 4.3 查看会话

点某把 Key 进入**只读**记录页，再返回列表。只打开这一把 Key 的时间线（该隐藏角色的 `GET /api/roles/{id}/timeline`）。不要在首页底下堆聊天，也不要按人设合并时间线。

两把 Key 选了同一人设：卡片上徽章同名，点进去是**两份互不相干的聊天**。折叠里的说话方式旁可写「N 把密钥在用」。

## 5. 并发：哪里不堵，哪里仍会排

| 场景 | 结果 |
|------|------|
| Key A 与 Key B 同时 `POST /api/v1/chat` | 两个工作角色、两把沙箱，**不堵** |
| 同一把 Key 同时两个请求 | 共用这一把沙箱；同会话会 409 `turn_in_progress`。P0：第二请求 409，或排队等该 Key 当前回合结束。不把同一 Key 拆成多沙箱 |
| 左栏某角色正在跑沙箱 | 不影响任何 API Key；反之亦然 |
| 四个左栏角色沙箱都占满 | API 仍能跑：`sandbox_max_roles` **只数左栏**。API 另有上限 `sandbox_max_api_roles`（建议默认 8），满则这把 Key 返回池满，**绝不借用**左栏或其它 Key 的盘 |
| API 角色空闲 | 与现网相同：TTL 只关容器、留卷，下次按原卷起来 |

低并发下 8 个 API 活容器够用；空闲会回收，不是「有多少 Key 就常驻多少容器」。

## 6. 能力与调用（未改）

`select_tools(mode=api)`：只读 KB + 读 Skill + 沙箱执行；无写库、无 `publish_from_sandbox`、无改角色/例行任务/记忆写入。`origin=api` 跳过网页沙箱确认。不跑记忆抽取。`recall_memory` 可只读。

Skill catalog =（Key 可选白名单，否则全局启用集）∩ 请求 `skills`。交集空 → 400。

```
POST /api/v1/chat
Authorization: Bearer lc_live_…
{ "message": "…", "conversation_id": null, "skills": ["技能/周报助手"], "title": "…", "stream": false }
```

- 不传 `conversation_id`：在**这把 Key 的工作角色**下新建会话
- 带 id：必须属于这把 Key，否则 404（A 的 id 不能拿去续 B）
- 角色/人设不由请求指定，避免脚本改绑到别人的工作角色
- **`stream: true`**：请求体仍是 JSON；响应为 `text/event-stream`。先 `start`（含 `conversation_id` / `turn_id`），再增量，最后 `done`（终答在 `message.content`）。思考 / 工具事件默认不下发，由通道卡片「思考」「工具」开关打开。不把网页用的 `timeline_state` 暴露给脚本。断开 SSE **不**取消回合。

```
event: start
data: {"conversation_id":"…","turn_id":"…","status":"running"}

event: text_delta
data: {"delta":"你好"}

event: done
data: {"conversation_id":"…","turn_id":"…","status":"completed","message":{"role":"assistant","content":"你好"}}
```

可选事件：`think_delta`（卡片开「思考」）、`tool_start` / `tool_progress` / `tool_result`（卡片开「工具」）、`error`。`done` 可能带 `needs_input`（征询纯文本）。终答以 `done.message.content` 为准。

其它：`GET/stop` 会话与回合、`GET /api/v1/skills`。网页 Cookie 做 Key CRUD + 读某把 Key 的时间线。Bearer 不能打设置/KB 树。

## 7. 存储与 seam

- `api_personas`（可放 `roles.db`）：`id, name, avatar, system_prompt`
- `roles`：`visibility`；每把 Key 一行 hidden；`persona_id`
- `api_keys.json`：`id, name, hash, prefix, persona_id, role_id, revoked, created_at, last_used_at`
- `conversations`：`origin, api_key_id`；tip/左栏排除 hidden 与 `origin=api`
- 池：`max_roles` 不计 hidden；`max_api_roles` 只计 hidden 活容器
- `PublicChatService`：验 Key → 取 `role_id` → `begin_persisted_turn`；注入人设用 `persona_id` 的当前文案
- `SandboxTools` 仍只按 `conversation.role_id` 取 slot，无特殊分支也能隔离

禁止：多把 Key 指向同一 `role_id`；API 会话写进左栏角色；请求里带一个左栏 `role_id` 去借用它的沙箱。

## 8. 分期

**P0**：人设 CRUD；创建 Key 必选/新建人设并生成隐藏角色；v1 chat + 按 Key 只读时间线；`mode=api`；API 沙箱不占左栏 4 名额；同 Key 并发 409。

**P1**：`thread_id`；**精简 SSE（`stream: true`）已落地**；设置页回答 `needs_input`；「改为独立人设」；删 Key 时是否毁卷。

**P2**：OpenAI 兼容适配；用量；附件。

## 9. 验收

1. 左栏没有任何 API 工作角色。
2. 两把 Key 选同一人设，同时调用：两份回复都成功，两套会话、两把沙箱；一方 stop 不影响另一方。
3. 点 Key A 只看到 A 的聊天；B 的一条都没有。
4. 改人设后，两把 Key 的下一轮都用新提示词。
5. 改左栏「通用」的人设，不影响任何 API Key（除非创建时从它复制过，且那是副本）。
6. 写库 / 回写 / 改 Skill 的工具不存在。
7. 四个左栏沙箱占满时，API Key 仍能启动自己的容器。
8. 同一把 Key 连打两枪未结束：第二枪 409，不借用其它 Key 的角色。

## 10. 明确不做

- 多把 Key 共用一个 `role_id`
- 按人设合并成一条大时间线
- 请求里指定左栏角色去跑
- 左栏出现这些工作角色
- 同一把 Key 再开多把沙箱
- ephemeral、自动写回 KB
- 把网页 `timeline_state` 原样暴露给脚本 SSE
