# 对外聊天 API（草案）

> 状态：**草案**（2026-09-12）。尚未落地代码。本文是实现对照规格；采纳后另写 ADR，不改写本文已拍板的决策段。
>
> 配套现状：[CONTEXT.md](../CONTEXT.md) 聊天持久化、[product-multi-role.md](product-multi-role.md) 角色时间线、[ADR 2026-09-10 timeline](adr/2026-09-10-role-timeline.md)、[ADR 2026-09-10 sandbox](adr/2026-09-10-role-scoped-sandbox.md)。

## 0. 已拍板

主人确认（2026-09-12）：

| 问题 | 决定 |
|------|------|
| 谁来调用 | **自己的脚本/自动化**。一般不给别人开，也没有很大并发。仍用 API Key（脚本不好走网页 Cookie），但按单操作者、低并发做，不做多租户、限流、OAuth。 |
| 历史展示 | **独立入口**，不进现有角色时间线，不和日常聊天混在一起。 |
| 知识库 / Skill | **不能改写**。可读、可按 catalog 跑 Skill，不能 `write_doc` / 改 Skill 文件 / 启用集 / 发布回库。 |
| 沙箱 | **可以跑**。但不能和现有角色的执行沙箱抢同一把容器、同一张盘，也不能互相 interrupt。 |
| 角色归属 | **待选**。见 §4：人设用谁、沙箱挂谁，是两件事。推荐方案 A。 |
| 会话 | 默认每次调用新建一段并落库。脚本若要多轮，可带返回的 `conversation_id`（或 P1 的 `thread_id`）。只在 API 会话之间接续，绝不续网页 tip。 |
| 首期响应 | 同步 JSON。超时 202 + 轮询。 |

## 1. 要解决的问题

Lore Chat 已经是带角色、Skill、知识库、工具循环的聊天机器人。网页主入口是 Cookie 登录后的 `POST /api/chat`（SSE，会话挂在角色时间线上）。

主人希望给**自己的脚本**开一个聊天接口：做好一个 Skill，外部 HTTP 调用，拿到工作回复；需要时在沙箱里跑命令。现有网页契约不适合：

- 鉴权只有 `lorechat_session` Cookie。
- `/api/chat` 绑定托盘、观测通道、内部 timeline 事件。
- 无 `conversation_id` 时走 ephemeral，不落库。
- 现网沙箱是**每角色一把容器 + 一张 PVC**（[ADR 2026-09-10](adr/2026-09-10-role-scoped-sandbox.md)）。API 若挂到某个已有角色上，会和该角色网页回合、定时任务抢 `/workspace`，一方 stop 会打断另一方。
- 角色时间线若混入 API 段，日常聊天被刷屏，tip 算法也会被 `updated_at` 带跑。

## 2. 目标与非目标

### 目标

1. 设置里签发/吊销一把（或多把）API Key，脚本用 `Authorization: Bearer` 调用。
2. 一次调用能跑指定 Skill，返回助手回复；允许沙箱执行。
3. API 会话在产品里**单独**可见，不进角色时间线。
4. 不改知识库、不改 Skill、不改角色/例行任务/记忆画像。
5. API 沙箱与角色沙箱隔离：不同 slot、不同卷、中断互不影响。
6. 内部仍走 `TurnExecutionHub` / `ChatSessionRunner`；HTTP 不解析 Agent SSE。

### 非目标

- 多租户、OAuth、按调用方计费、高并发限流。
- 把 `/api/chat`、知识库树、设置原样对外。
- API ephemeral（不落库）。
- 调用方上传整份 `SKILL.md`。
- 首期 OpenAI `/v1/chat/completions` 兼容（P2 适配层）。
- API 会话出现在角色时间线，或虚构一个出现在左栏的「开放接口」聊天角色（方案 A 的系统角色**不进**左栏角色列表）。
- API 借用任一现有角色的 sandbox slot。

## 3. 产品模型

```
脚本 --Bearer Key--> /api/v1/chat
                        │
                        ├─ 只读工具集 + 沙箱工具（无写库 / 无改 Skill / 无回写 KB）
                        ├─ 会话：新建或续 API 自己的 conversation
                        ├─ 人设：按 §4 所选方案注入
                        └─ 沙箱：只打 reserved API slot（§5）
                                  │
网页「开放接口」页 <── 同一 ConversationStore，origin=api
角色时间线 / tip / 左栏最近活动  ──  完全不看这些行
角色沙箱 slot                   ──  完全不碰
```

Key 只能碰它自己创建的 `origin=api` 会话。网页 Cookie 不能当 v1 凭证，Bearer 不能调设置/KB 树。

## 4. 角色：人设与沙箱要拆开

现网「角色」同时决定三件事：人设（`system_prompt`）、会话挂在哪条时间线、沙箱 slot（`RoleSandboxPool.get(role_id)`）。API 不能原样复用，否则：

- 挂到「通用」上 → 时间线混在一起，且和通用角色抢沙箱；
- 随便指定一个角色 → 该角色正在聊或跑定时任务时，API `sandbox_run` / stop 会踩同一张盘、打断同一进程。

所以先拆：

| 维度 | 含义 | API 侧约束 |
|------|------|------------|
| 人设 | 心法/戒律之外，还要不要叠某个人设 | 见下面三套方案 |
| 会话归属 | 历史显示在哪 | **固定**：只进「开放接口」页，`origin=api`，不进任何角色时间线 |
| 沙箱 slot | 哪把容器、哪张 PVC | **固定**：专用 API slot，见 §5。不随人设走 |

跨方案不变：会话独立展示；沙箱永不 `get(某个现有聊天角色)`。

### 方案 A — 隐藏系统角色（推荐）

系统内置一个不出现在左栏的角色，id 建议 `__api__`（名称「开放接口」，不可删）。

- 人设：可在「开放接口」页编辑（可空）。空则只靠心法/戒律 + Skill。
- 会话：`role_id=__api__` + `origin=api`；角色时间线查询直接排除 `__api__`。
- 沙箱：slot 就是 `__api__`，和现有角色天然不是同一把。

适合：脚本只是「跑某个 Skill 拿回复」，不需要对外假装成某个聊天角色。实现最小，和独立展示一致。

代价：API 默认没有「分析师」「老师」那种人设，除非你在开放接口页写一份，或把风格写进 Skill。

### 方案 B — 人设借用现有角色，沙箱仍走 API slot

创建 Key（或每次请求）指定一个已有 `role_id`，只把该角色的 `system_prompt` / 名称注入 Agent。

- 会话：仍然 `origin=api`，**不**出现在该角色时间线。
- 沙箱：**仍然只打 API slot**。禁止 `pool.get(被借人设的 role_id)`。
- 存储：`persona_role_id`（人设）与 `role_id`/`sandbox_slot`（执行）分开。

适合：已经给某个角色写好了人设，希望脚本里的口气和它一致，但执行环境必须分开。

代价：两套 id，实现和心智都多一截；该角色改人设会马上影响 API。

### 方案 C — 每次请求自己选人设角色

和 B 一样拆人设/沙箱，但 `role_id` 由当次请求传入（须是已有角色，或省略则用 Key 默认 / 空人设）。

适合：同一把 Key，有的脚本要角色甲的口气，有的要角色乙。

代价：脚本要知道角色 id；一般自己用、低并发，用不上这么灵活。

### 方案 D — 无人设（不推荐作唯一方案）

不引入系统角色，也不借人设。只注入心法/戒律 + Skill + 只读检索。沙箱仍是 API slot。

太瘦：主人已经问「用什么角色跑」，说明需要一个明确归属；没有系统角色时，会话行的 `role_id` 还是得找个不进时间线的值，最后会滑回 A。

### 不采用

- **API 直接跑在「通用」或任一现有角色上**（人设、时间线、沙箱绑在一起）：和「独立展示」「沙箱不冲突」都矛盾。
- **左栏再摆一个可切换的聊天角色叫「开放接口」**：又和日常聊天混在同一套中栏里。
- **每个 thread / 每把 Key 一把沙箱**：低并发不需要，会占满 `sandbox_max_roles`。

### 推荐

**先做 A**。开放接口页可以写人设；真要借用某个角色口气，再加 B（Key 上一个可选 `persona_role_id`），沙箱契约不变。

## 5. 沙箱隔离（已定）

现网：`opensandbox-server` ×1；每个**已激活角色**一把 agent 容器 + 一张 PVC；`interrupt` 只打该角色；满员（默认 4）且不能回收时空错 `sandbox_pool_full`，**永不借用**他人 slot。同角色多会话靠 `/workspace/conversations/{cid}` 分目录。

API 必须能 `sandbox_run`，但：

1. **专用 slot** `api`（方案 A 下即 `__api__`）。卷名例如 `lorechat-sandbox-ws-api`，不复用 `lorechat-sandbox-workspace`（那是默认角色的盘）。
2. **解析路径**：`origin=api` 时 `SandboxTools` / stop / pending 只认 API slot。即使方案 B 填了 `persona_role_id`，也不得 `get(persona_role_id)`。
3. **中断**：停 API 回合只 interrupt API slot；停某个聊天角色不影响 API。禁止对 API 走跨角色 `interrupt_all`。
4. **cwd**：`/workspace/conversations/{conversation_id}`，约定与现网交互回合相同，只是盘不同。
5. **池容量（推荐）**：API slot **不占** `sandbox_max_roles` 那 4 个角色名额。角色并行上限保持原义；API 另有 1 个活容器。空闲 TTL 同样可收回 API 容器、留卷。低并发下同时最多「4 个角色 + 1 个 API」。
6. **满员**：四个聊天角色都占着时，API 仍能跑（因为预留）。不要让 API 和第五个新角色去抢；也不要在满员时借用角色盘。
7. **高风险确认**：脚本自动化等不了网页点批准。`origin=api` **跳过** `SandboxCommandGate` 网页确认，直接执行。风险靠「只有自己持有 Key + 不能 publish 回 KB」收住。不在首期做 `auto_approve` 开关。
8. **不能回写知识库**：保留 `sandbox_run` / `stage_to_sandbox` / 读文件 / 列目录 / stop / job_status；**去掉** `publish_from_sandbox`。沙箱里的产物停在 API 自己的卷上，不进 KB、不改 Skill。

现成 `select_tools(mode=no_write)` 已去掉 `write_doc` / `write_kb_file` / `update_doc_meta` / `manage_memory` / `publish_from_sandbox`。API 还要再去掉 `edit_doc`、`summarize_conversation`、`move_entry`、`delete_kb`、以及全部角色 CRUD / 例行任务工具。建议新增 `mode=api`（或等价 allowlist），不要在提示词里堆黑名单。

## 6. 会话模型

### 6.1 默认：每次新开一段

不传 `conversation_id` / `thread_id`：`create` 一条 `origin=api` 会话，跑一轮，返回 `conversation_id`。适合一次 Skill 作业。

### 6.2 可选接续

带上次返回的 `conversation_id`（须 `origin=api` 且属于这把 Key）：在同一段上追加，Agent history 含前轮。同一会话仍只能一个 running turn。

P1：`thread_id`（脚本自己的键，如 `cron:weekly`）映射到上述会话，免记 Lore id。

### 6.3 不采用

- ephemeral；一个 Key 永远一条会话；续网页会话；跨 Key 共享 id。

## 7. 历史如何展示（独立，已定）

不进 `GET /api/roles/{id}/timeline`，不进左栏角色「最近活动」，不进中栏筛选。

设置（或左栏知识库下方一个**非角色**入口）→ **开放接口**：

1. Key：创建（显示一次）、吊销、上次使用。
2. 人设：方案 A 下编辑系统角色人设；方案 B 下选择借用哪个角色。
3. 会话列表：标题、时间、状态；点开只读 transcript（可看工具/沙箱日志，与网页历史段同类渲染）。
4. 调用示例：`POST {public_base_url}/api/v1/chat`。

标题：请求 `title`，否则首条用户消息截断。

工作区搜索（Ctrl+K）默认**不含** `origin=api`；需要时加 scope「开放接口」。避免脚本垃圾进日常检索。

tip / `ensure_active` / `open_new_topic` / 角色最近开聊：**只看 `origin=web`**。API 更新 `updated_at` 也不许把主人 tip 抢走。这是隔离的第二道，即使有人误把 API 行写成某个 `role_id` 也不进 tip。

网页「继续此段」做成日常聊天：**不做**。要接着聊走 API 再带 `conversation_id`。

`ask_user`：API 返回 `needs_input`；开放接口页也可回答。不要把征询混进主人正在聊的中栏。沙箱已跳过确认，这类 pending 会少很多。

## 8. 鉴权与 Key

```
Authorization: Bearer lc_live_<secret>
```

明文只在创建时显示一次；落盘哈希 + `key_prefix`。`{kb}/.kb/api_keys.json`。

字段从简（自己用、低并发）：

| 字段 | 含义 |
|------|------|
| `id` / `name` | 内部 id、显示名 |
| `skills` | 可选白名单；空 = 当前全局启用集 |
| `persona_role_id` | 仅方案 B/C |
| `revoked` | 吊销即 401 |

不设 `kb_write` / `sandbox` 勾选：写库永远关，沙箱永远开（实例开了沙箱的前提下）。不配 CORS、不配速率限制。

中间件：仅 `/api/v1/*` 认 Bearer。Key 不能打 `/api/settings`、`/api/kb/*`。`GET /api/health` 仍公开。

## 9. Skill

- 包必须在「技能」目录，有合格 YAML 头。
- catalog = `（Key.skills 或全局启用集） ∩ 请求.skills（若传）`。
- 交集为空 → 400，不退化成无 Skill 闲聊。
- 只 `read_doc` Skill 正文，不能改文件、不能 `PUT /api/enabled-skills`。
- 不按 Skill 名做关键词黑名单。

## 10. 对外 HTTP 契约

前缀 `/api/v1`。错误 `{"code","message"}`。

### 10.1 `POST /api/v1/chat`

```json
{
  "message": "用周报助手把下面材料整理成周报：…",
  "conversation_id": null,
  "thread_id": null,
  "skills": ["技能/周报助手"],
  "title": "2026-W37 周报",
  "role_id": null,
  "wait": true,
  "timeout_sec": 120
}
```

| 字段 | 说明 |
|------|------|
| `message` | 必填。首期无附件；材料放进正文或主人事先写入 KB 再让 Skill 去读。 |
| `conversation_id` | 续 API 会话。 |
| `thread_id` | P1。 |
| `skills` | 当次收窄。 |
| `title` | 仅新建。 |
| `role_id` | 仅方案 C；A/B 忽略或校验后 400。 |
| `wait` / `timeout_sec` | 默认等 120s，上限 600；超时不取消回合。 |

完成：

```json
{
  "conversation_id": "a1b2c3d4e5f6",
  "turn_id": "…",
  "status": "completed",
  "message": { "id": "…", "role": "assistant", "content": "…" },
  "usage": { "input_tokens": 0, "output_tokens": 0 }
}
```

`status`：`completed` \| `running` \| `needs_input` \| `failed` \| `stopped`。超时 202 + `running`。

### 10.2 其它

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/conversations` | 本 Key 的 API 会话 |
| GET | `/api/v1/conversations/{id}` | 消息；可 `tail` |
| GET | `/api/v1/conversations/{id}/turns/{turn_id}` | 回合状态 |
| POST | `/api/v1/conversations/{id}/stop` | 只停该会话，interrupt API slot |
| GET | `/api/v1/skills` | 可用 catalog |
| POST | `/api/v1/questions/{id}/resolve` | P1 |

越权 → 404。网页用 Cookie 调 `/api/open-api/*`（名称可再定）列全部 API 会话，不走 v1。

### 10.3 示例

```bash
curl -sS "$LORECHAT/api/v1/chat" \
  -H "Authorization: Bearer lc_live_…" \
  -H "Content-Type: application/json" \
  -d '{"message":"把这段会议记录写成纪要：…","skills":["技能/会议纪要"]}'
```

## 11. 记忆

API 会话**不**跑 `SessionMemoryObserve` / 记忆抽取，也不提供 `manage_memory`。脚本内容和 Skill 作业不是主人画像；这也属于「不具备修改能力」。

`recall_memory` 可以保留：只读已有画像，帮助 Skill 说话，但不写回。

## 12. 存储与 seam

`conversations` 增加：

- `origin TEXT NOT NULL DEFAULT 'web'`
- `api_key_id TEXT`
- `external_thread_id TEXT`（P1）
- `persona_role_id TEXT`（仅方案 B/C）
- 索引 `(origin, updated_at)`、`(api_key_id, updated_at)`

方案 A：`role_id='__api__'`。时间线 / tip / 角色列表均排除该 id 与 `origin=api`（两道过滤）。

`RoleSandboxPool`：slot 键允许非左栏角色（`__api__`）。`max_roles` 统计**不含** API slot；API `get` 走独立预留。`SandboxTools` 对 `origin=api` 固定 API slot。

| 层 | 职责 |
|----|------|
| `AuthMiddleware` | `/api/v1/*` Bearer |
| HTTP `v1_routes` | DTO / 状态码 / 可选 SSE；不解析内部事件 |
| `PublicChatService` | 会话、catalog、`select_tools(mode=api)`、等回合结束、投影 |
| `ChatSessionRunner` / Hub | 不分来源；多 origin / skill_catalog / tool mode |
| `ConversationStore` | tip/timeline 排除 api；create 带来源字段 |
| 设置「开放接口」 | Key、人设、会话列表与只读 transcript |

禁止：在 `chat_routes.py` 加 `if api_key`；API `ensure_active_conversation`；为 API 另写 Agent 循环；`origin=api` 时 `pool.get(普通角色)`。

## 13. 分期

**P0**

- Key + `POST /api/v1/chat` 同步（新建或 `conversation_id` 续）+ 202
- GET 会话/回合、stop、GET skills
- `origin=api` 落库；角色时间线/tip/搜索默认不可见
- 设置「开放接口」：Key + 会话列表 + 只读 transcript
- `select_tools(mode=api)`：只读 KB + Skill 读取 + 沙箱，无写库/无回写/无改角色
- 专用 API 沙箱 slot，不占 4 角色名额，跳过网页沙箱确认
- 方案 A 系统角色（若采用 A）

**P1**

- `thread_id`
- 精简 SSE
- 开放接口页回答 `needs_input`
- 方案 B 的可选 `persona_role_id`（若先做 A）

**P2**

- OpenAI 兼容适配
- 用量展示
- 附件

## 14. 验收意图

1. 无 Key / 坏 Key → 401；Cookie ≠ v1，Bearer ≠ 网页管理接口。
2. 不传会话 ID → 新 `origin=api` 行；角色时间线、tip、左栏最近活动都不变。
3. 开放接口页能看到该段全文；角色时间线看不到。
4. 带返回的 `conversation_id` → 同段接续。
5. 指定 skills 交集空 → 400。
6. 模型即使想 `write_doc` / `publish_from_sandbox` / `delete_kb` → 工具不存在。
7. API `sandbox_run` 打在 API 卷；同时网页某角色 `sandbox_run` 打在该角色卷；一方 stop 不影响另一方。
8. 四个聊天角色沙箱都占着时，API 仍能启动自己的容器。
9. 方案 A：左栏角色列表没有「开放接口」。方案 B：借用人设时该角色时间线仍无 API 段，且 `pool.get` 不是该角色。

## 15. 明确不采用

- 复用 `/api/chat` 加 header
- API 默认 ephemeral
- API 挂到通用/任一现有角色并共用其沙箱
- 时间线混布 + 筛选权当「独立」
- 用提示词禁止写库，而工具仍挂着
- 为 API 另写记忆抽取提示词（直接不抽取）
- 首期只做 OpenAI 兼容

## 16. 待你选的一口

角色方案选 **A / B / C**（推荐 A）。沙箱隔离与独立展示、只读知识库/Skill 不再改口径，除非你明确推翻。
