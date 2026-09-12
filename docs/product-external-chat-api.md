# 对外聊天 API

> 状态：**已确认 / 实现中**（2026-09-12）。人设可共享；**每把 API Key = 一个独立隐藏角色**（独立沙箱、独立会话）。
>
> 配套：[CONTEXT.md](../CONTEXT.md)、[product-multi-role.md](product-multi-role.md)、[ADR 2026-09-10 timeline](adr/2026-09-10-role-timeline.md)、[ADR 2026-09-10 sandbox](adr/2026-09-10-role-scoped-sandbox.md)。

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
| 展示 | 不进左栏，不进日常角色时间线。入口在设置 → 开放接口。 |
| KB / Skill | 可读、可跑 Skill；不能改 KB、不能改 Skill、不能沙箱回写。 |
| 沙箱 | 能跑。每个工作角色一把容器/卷，与左栏角色互不 interrupt。 |
| 会话 | 默认每次调用新建一段；可带该 Key 自己的 `conversation_id` 多轮。 |
| 响应 | 同步 JSON；超时 202。 |

## 3. 数据怎么落

创建一把 Key 时系统做三件事：

1. 写入 Key（哈希、名称、`persona_id`、`role_id`）。
2. `roles.create`：`visibility=hidden`，`id` 如 `api_<key短id>`，`onboarding_status=completed`，不可当默认、不进左栏、不可从左栏删。
3. 工作角色挂上 `persona_id`。Agent 注入时**读人设的当前提示词**（活引用，不是创建时拷死一份）。改人设，所有选用它的 Key 下一轮生效。某一把 Key 要走样：在 Key 上「改为独立人设」（复制出一份新 persona，只属于它）。

会话：`role_id = 该 Key 的工作角色`，`origin=api`，`api_key_id = 这把 Key`。

沙箱：`RoleSandboxPool.get(该工作角色 id)`。现网「永不借用其它角色」直接成立，不必再发明第三种 slot。

左栏 `GET /api/roles` 只返回 `visibility=sidebar`。`ensure_active` / tip / 最近活动只看 `origin=web`。

吊销 Key：不能再调 v1，**历史和工作角色留下**，设置里仍能看日志。删除 Key（P1）：可选毁掉该角色沙箱卷。

## 4. 界面（把「同人设 / 独立干活」做清楚）

设置 → **开放接口**，两块。

### 4.1 人设

可建多套。每套：名称、头像、提示词。没有 Key 在用也可以先写好。

提供「从左栏角色复制人设」（只拷名称/头像/提示词，**不**绑那个角色的沙箱和聊天）。

### 4.2 密钥

创建时：

- 密钥名称（如「周报脚本」「给同事甲」）
- **使用人设**：选已有一套，或当场新建一套

列表每一行是一把 Key，也是一个独立工作角色：

- 密钥名、前缀、所用人设名、上次调用
- **查看会话**：只打开**这一把 Key** 的时间线（该隐藏角色的 `GET /api/roles/{id}/timeline`）
- 吊销

两把 Key 选了同一人设：列表上人设名相同，点进去是**两份互不相干的聊天**。不要做成「点人设看所有 Key 的合并时间线」（那又混了）。若要对比，只在人设旁写「被 N 把密钥使用」。

时间线组件与主界面其它角色相同（分段、正文、工具卡、沙箱日志）。P0 只读，不在设置里放输入框。

创建 Key 时明文只显示一次。

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
{ "message": "…", "conversation_id": null, "skills": ["技能/周报助手"], "title": "…" }
```

- 不传 `conversation_id`：在**这把 Key 的工作角色**下新建会话
- 带 id：必须属于这把 Key，否则 404（A 的 id 不能拿去续 B）
- 角色/人设不由请求指定，避免脚本改绑到别人的工作角色

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

**P1**：`thread_id`；精简 SSE；设置页回答 `needs_input`；「改为独立人设」；删 Key 时是否毁卷。

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
