# 公开演示站：访客只读模式与演示内容

日期：2026-08-18
状态：设计已确认，待实施计划
前置：当前产品为单实例单用户（`AuthMiddleware` 单密码门禁、一个 KB、一个 `conversations.db`），无访客概念、无只读模式、无演示内容。

## 1. 目标

让任何人打开一个公网地址，无需注册即可体验 Lore，并在几分钟内理解「对话 → 知识 → 记忆 → Skill」这条主线，同时不会破坏系统。

1. **访客可读全貌**：知识库目录树与文档、预置历史会话的完整时间线、记忆面板、技能目录、设置页（只读）、用量页。
2. **访客可提问**：正常走 Agent 回答，但对话不落库、不产生记忆、不写知识库。
3. **访客不可修改**：任何写操作在 HTTP 层与 Agent 工具层都被拒绝，且默认关闭而非默认开放。
4. **预置内容制造 wow**：一份有厚度、可交叉跳转的知识库与六条成长弧会话。

非目标（本期不做）：

- 多用户账号、配额账户体系、访客数据留存
- 访客可写的沙盒目录、按访客克隆实例
- 沙箱执行与生图在演示站的可用性（靠预置会话记录展示）

## 2. 已确认决策

| 项 | 决策 |
|----|------|
| 隔离模型 | 所有访客共用一个实例，硬只读 |
| 访客身份 | `DEMO_MODE` 下自动签发访客 cookie，无需密码；管理员仍可用密码登录 |
| 只读实现 | 白名单中间件（默认拒绝），叠加 Agent 工具层与 `KnowledgeWriter` 兜底 |
| 写意图表现 | 写工具换成「预览式」实现：真实跑归位与成文，返回 `preview_only`，不落盘 |
| 追问能力 | 支持从预置会话分叉出临时会话（`ephemeral_from`），带上下文但不持久化 |
| 联网搜索 | 保留（带限流）；`fetch_url` 关闭 |
| 整库下载 | 关闭 `/api/download-zip`；单篇文档下载保留 |
| 内容主题 | 一位 AI 产品/技术从业者的知识空间（教育科技场景锚点） |
| 内容生产 | 空库起步，剧本驱动真实 API 跑出内容，人工直接修改定稿 |
| 内容固化 | 定稿内容以纯文本进 git（Markdown 原样 + 会话/记忆 JSON），SQLite 不进 git |
| 时间戳 | 构建时按「距今多少天」整体平移 |

## 3. 架构总览

```
访客浏览器
   │  lore_guest cookie（内存 session，TTL 2h）
   ▼
AuthMiddleware ── DEMO_MODE ──▶ 解析身份 admin | guest → request.state.identity
   │
   ▼
DemoGuardMiddleware ── guest 且不在读白名单 ──▶ 403 { code: "demo_read_only" }
   │
   ▼
路由层 ── /api/chat：guest 断言必须 ephemeral（无 conversation_id，或仅 ephemeral_from）
   │
   ▼
AgentToolLoop ── demo 工具目录（读工具 + 预览式写工具）
   │
   ├── ToolRegistry.execute      硬拒写工具名（兜底）
   └── KnowledgeWriter           demo 下拒绝一切写入（唯一写入 seam 兜底）
```

新增/改动模块：

| 模块 | 职责 |
|------|------|
| `app/demo/config.py` | `DEMO_MODE` 读取与常量（TTL、限流阈值、白名单） |
| `app/demo/guest_sessions.py` | 进程内访客 session 存储（不落盘） |
| `app/demo/guard.py` | `DemoGuardMiddleware` 读白名单 |
| `app/demo/quota.py` | 按访客 / 按 IP / 全站每日限流 |
| `app/engine/agent/tool_catalog.py` | 按 demo 装配工具目录 |
| `app/engine/agent/tool_impl/demo_preview.py` | 预览式 `write_doc` / `edit_doc` / `manage_memory` 等 |
| `frontend` | `useDemoCapability()` 统一能力判定 + 演示条 + 引导 + 403 兜底 |
| `demo/` | 剧本、seeding 脚本、dump/load 工具、定稿内容、构建脚本 |

## 4. 开关与身份

### 4.1 DEMO_MODE

- 来源：进程环境变量，`Settings.demo_mode: bool = False`。
- **必须加入 `EDITABLE_SETTING_KEYS` 的排除集**，与 `sandbox_enabled` 同类：这是部署级能力开关，不能从设置页热改。否则演示站可以被访客或误操作从 UI 关掉只读。

### 4.2 身份解析

`AuthMiddleware` 扩展为解析身份并写入 `request.state.identity`：

| 身份 | 判定 | 权限 |
|------|------|------|
| `admin` | 有效 `lore_session` cookie | 现有全部权限，不受 demo 限制 |
| `guest` | `DEMO_MODE` 且有效 `lore_guest` cookie | 读白名单 + 临时提问 |
| 无 | 其余 | 非 demo：401；demo：自动签发访客 cookie |

新增 `POST /api/auth/guest`（demo 下公开）：签发访客 cookie 并返回身份。前端首访 `GET /api/auth/status` 若得到 `{ demo: true, authenticated: false }` 则调用它。

`GET /api/auth/status` 在 demo 下额外返回 `{ demo: true, role: "guest" | "admin" }`，前端据此跳过登录门。

### 4.3 访客 session 存储

**不复用 `SessionStore`。** 现有实现每次 `validate()` 都因滑动过期重写 `.kb/sessions.json`，公开站的并发访客会把该文件写成瓶颈与竞态源，而且会把演示数据目录变脏。

访客 session 用进程内字典：

- TTL 2 小时，惰性清理
- 容量上限（如 10000），超出按最旧淘汰
- 不落盘；进程重启后访客自动重新签发
- 记录 `created_at` / `message_count` / `ip`，供限流使用

### 4.4 demo 下必须关闭的鉴权入口

- `POST /api/auth/setup`：demo 下一律 403。黄金快照虽已设密，但一旦缺失，任何访客都能抢先把自己设成管理员。
- `POST /api/auth/change-password`：不在读白名单内，自然被拒。

## 5. 只读门禁：白名单

### 5.1 为什么是白名单

黑名单意味着以后任何人新增一个写接口，演示站就默默开了个洞——这是「加一个接口 = 一次潜在事故」的结构。白名单是默认关闭：忘了加白名单，最坏结果是某个只读功能在演示站不可用，属于可发现、不致命的失败。

### 5.2 GET 白名单

```
/api/health
/api/auth/status
/api/tree
/api/doc
/api/download
/api/attachments/signed/{path}
/api/conversations
/api/conversations/{cid}
/api/conversations/{cid}/events
/api/conversations/{cid}/turns/active/stream
/api/questions
/api/memory/facts
/api/kb/discover-skills
/api/enabled-skills
/api/docs/merge/active
/api/docs/merge/{merge_id}
/api/admin/settings
/api/admin/settings-attention
/api/admin/model-catalog
/api/usage/summary
/api/usage/events
/api/usage/prices
/api/usage/prefs
```

明确**不在**白名单（即使是 GET）：

- `GET /api/admin/export`：导出包含 `auth.json` 与明文密钥的 `settings.json`。
- `GET /api/download-zip`：整库打包，纯带宽滥用面，对演示无价值。

### 5.3 POST 白名单

仅两条：

- `POST /api/auth/guest`
- `POST /api/chat`

其余方法（POST / PUT / PATCH / DELETE）在 guest 身份下一律 403 `{ "code": "demo_read_only", "detail": "演示环境为只读" }`。

### 5.4 /api/chat 的临时性断言放在路由层

中间件不读请求体。Starlette 的 `BaseHTTPMiddleware` 读 body 后需要重新注入才能被路由消费，容易埋坑。因此：中间件放行 `POST /api/chat`，由 `chat_routes.chat()` 在 guest 身份下断言：

- `conversation_id` 必须为空 → 否则 403 `demo_read_only`
- 允许 `ephemeral_from`（见 §7）

### 5.5 设置页密钥的二次遮蔽

`SettingsStore.public_dict()` 目前把密钥脱敏为 `前2位***后4位`。对一个匿名公开页面，泄漏真实密钥的头尾仍然是泄漏。

demo 下 guest 读取 `GET /api/admin/settings` 时，所有密钥字段（含 `chat_models[].api_key`、`search_providers[].api_key`、`image_providers[].api_key` 等链式嵌套）**整体替换为 `"***"`**，不保留任何片段。`base_url` / 模型名可以保留，它们正是要展示的「多模型路由」能力。

## 6. Agent 侧：三层防写 + 预览式写工具

只读不能只拦 HTTP。临时对话虽不落库，但 Agent 工具会直接写共享 KB。

### 6.1 三层

1. **工具目录裁剪（模型层）**：demo 下装配 demo 版工具目录。模型看不见的工具不会被调用。这比在提示词里写「禁止写入」可靠——符合项目规范「能确定性做的不要交给模型」。
2. **`ToolRegistry.execute` 按名硬拒（执行层）**：模型幻觉出工具名也进不去。
3. **`KnowledgeWriter` 拒绝（写入 seam）**：`CONTEXT.md` 已确立它是唯一写入口，在此加一道 demo 断言，成本极低，覆盖所有绕行路径。

### 6.2 工具分类

| 处理 | 工具 |
|------|------|
| 原样保留 | `search_kb`、`read_doc`、`read_doc_meta`、`list_kb_structure`、`read_conversation_context`、`recall_memory`、`ask_user`、`web_search` |
| 换成预览式（同名同 schema） | `write_doc`、`edit_doc`、`summarize_conversation`、`manage_memory`、`update_doc_meta` |
| 移除 | `write_kb_file`、`move_entry`、`delete_kb`、`generate_image`、`fetch_url`、`sandbox_run`、`sandbox_job_status`、`sandbox_list_dir`、`sandbox_read_file`、`publish_from_sandbox`、`stage_to_sandbox` |

移除项的理由：

- `fetch_url`：让匿名访客指定任意 URL 由服务器去拉，是真实的 SSRF 与滥用面。
- `generate_image`：按次付费，匿名访客可无限触发。
- `sandbox_*`：演示站不部署沙箱。
- `move_entry` / `delete_kb`：预览一次移动或删除难以呈现价值，而风险不对称。

这些能力靠预置会话里的真实历史记录来展示，访客仍能看到它们存在过。

### 6.3 预览式写工具

保持**同名同 schema** 是刻意的：这样系统提示词、Skill 沉淀下来的方法、以及模型的调用习惯都不需要为 demo 改写。

`write_doc` 在 demo 下的实现：

1. 真实跑 `PlacementPlanner`，得到 `directory` + `filename` + new/merge 决策
2. 真实跑文档成文
3. 返回 `{ "status": "preview_only", "would_write": { "path": "...", "mode": "merge" | "new" }, "content": "..." }`
4. 发出时间线事件 `demo_preview_doc`，前端渲染为「将写入：技术/检索/向量库选型对比.md · 演示环境未落盘」的预览卡，卡内是完整 Markdown

`manage_memory` 同理，产出「将记住：…」卡。

**诚实性保证**（两层，缺一不可）：

- 工具返回值显式带 `preview_only` 与不落盘说明，模型不会宣称「已保存」。
- demo 系统提示追加一段**环境契约**：说明当前为公开演示环境，知识库与记忆为只读，写类工具只产出预览。这是环境层的原则表述，不是针对具体话术打补丁。

## 7. 从预置会话追问：`ephemeral_from`

访客读完一条精心设计的会话后想追问一句，是转化率最高的时刻。但带 `conversation_id` 的 `POST /api/chat` 会落库。

新增可选参数 `ephemeral_from: <cid>`：

- 加载该会话的 transcript 作为上下文（复用现有的 transcript 打包逻辑）
- 走 `stream_ephemeral`，不写任何消息、turn、outbox、记忆
- 前端在预置会话页提供「从这里继续提问（不保存）」按钮，分叉出一个临时会话并保留上下文

管理员身份同样可用该参数（无害），不做身份特判。

## 8. 限流与成本

全部在进程内计数，不落盘。

| 维度 | 默认阈值 | 超限响应 |
|------|----------|----------|
| 单访客 session 消息数 | 20 条 | 403 `demo_quota_exceeded` |
| 单 IP 每小时消息数 | 60 条 | 403 `demo_quota_exceeded` |
| 全站每日消息数 | 可配，默认 2000 | 403 `demo_quota_exceeded` |
| 并发进行中回合 | 可配，默认 10 | 429 `demo_busy` |
| 单条输入字符数 | 2000 | 400 |
| `agent_max_tool_calls` | demo 下降到 10 | — |

所有超限文案要友好且带 CTA（「演示额度已用完，可以部署你自己的 Lore」）。计量复用现有 usage recorder，便于观察真实成本。

## 9. 前端

### 9.1 能力判定收在一处

新增 `useDemoCapability()`，返回 `{ isDemo, role, canWrite, canChatPersist }`。组件按能力渲染，**不允许**在各处散写 `if (demo)`。需要按能力关闭的入口至少包括：

- 侧栏：新建目录/文档、上传、拖拽移动、右键菜单中的写项
- 文档：编辑按钮、保存、元数据编辑
- 记忆面板：确认 / 编辑 / 遗忘 / 拒绝
- 设置页：全部保存按钮、改密、导入导出、重建索引、清冷却
- 合并工作流：发起合并、接受、拒绝
- 用量页：改价目表、清空

### 9.2 演示条与引导

- 顶部常驻一条：「演示环境 · 只读 · 对话不保存」+「部署你自己的 Lore」CTA
- 首访三步引导：① 左侧知识库树 ② 首屏高光会话 ③ 输入框可以直接提问
- 页脚一行小字：演示内容为虚构示例

### 9.3 兜底

全局拦截 403 `demo_read_only` → 统一 toast「演示环境不可修改」。任何遗漏的写入口即使被点到，也不会给出误导性的失败信息。

## 10. 演示内容设计

### 10.1 人物

**林知遥**，独立开发者带一个小团队，在做面向教培场景的 AI 学习产品。

选这个人设的原因：技术内容（检索、Agent 工程、模型路由）对所有 AI 从业者通用，「教育」只提供一个具体场景锚点，让访谈纪要、竞品调研这类内容有落点。所有访谈对象用化名。

### 10.2 目录树

约 24 篇文档，刻意不均匀——真实知识库不会每个目录恰好四篇。

下面文件名里的 `xx` 不是待填占位符：这些日期由 §11.4 的时间戳平移在构建时决定，定稿时写入的是真跑当天的日期。

```
系统/
  戒律.md
  心法.md
技能/
  周报生成/SKILL.md、模板.md
  竞品调研/SKILL.md、调研维度清单.md
产品/
  定位与叙事.md
  路线图与取舍.md
  用户访谈/
    2026-xx-xx 王老师（初中数学）.md
    2026-xx-xx 小型教培机构负责人.md
    访谈问题库.md
技术/
  检索/
    混合检索与 RRF.md
    向量库选型对比.md
    分块策略实验记录.md
  Agent 工程/
    工具设计原则.md
    上下文预算与渐进披露.md
    失败重试与降级.md
  模型/
    多模型路由与冷却.md
    识图能力实测.md
调研/
  2026 开源记忆层横评.md
  AI 学习产品竞品扫描.md
运营/
  周报/2026-Wxx.md ×3
灵感/
  碎片想法.md
```

### 10.3 六条会话

设计的关键不在单条会话多精彩，而在于**能顺着链条走**：会话产出的文档在树里点得开，文档能跳回来源会话，后面的周报又引用前面的文档。这个交叉引用网络是 demo 的骨架。

| # | 会话 | 展示能力 | 产出 |
|---|------|----------|------|
| 1 | 做 AI 学习产品，检索这块怎么选型 | 联网搜索 + 多来源对比 + 落库；时间线可展开看到真实 query 与来源 | 《向量库选型对比》 |
| 2 | 昨天那篇选型笔记，补上实测的分块参数 | `edit_doc` 局部编辑（看得到精准改动的那一段，而非整篇重写） | 更新选型对比 + 新建《分块策略实验记录》 |
| 3 | 把这段访谈原文整理一下 | 非结构化 → 结构化；AI 判断归位到 `产品/用户访谈/`，用户全程未指定路径 | 一篇访谈纪要 + 追加问题库 |
| 4 | `技术/检索` 下这几篇有重叠，合一下 | 多文档合并的审阅会话 | 目录收敛 |
| 5 | 按周报 Skill 出这周的周报 | Skill 启用 → 按沉淀方法读多篇资料 → 跑完整流程 | 《周报 Wxx》 |
| 6 | 下周要跟一家教培机构谈合作，帮我准备材料 | 跨会话记忆生效：未交代背景，却知道产品方向、目标用户、时间约束、输出偏好，并主动引用访谈纪要与周报 | 合作材料 |

**首屏高光会话是 #1**，因为它一屏之内讲完「对话 → 知识」的完整闭环，自解释性最强。#6 的震撼依赖读过前面的内容，放在新手引导的第三站。

### 10.4 记忆面板：对外的记忆质量样板

演示站的记忆面板是给外人看的，里面放什么就等于对外示范什么叫「该被记住的画像」。因此预置事实必须严格通过 `AGENTS.md` §2 的三道门槛（关于主人 / 耐久性 / 语境保全）。

**放**

| 事实 | 通过的门槛 |
|------|------------|
| 独立开发者，在做面向教培场景的 AI 学习产品 | 归属：主人身份 |
| 长期方向是教育科技 | 耐久：跨会话成立 |
| 希望先给结论再给依据 | 协作方式 |
| 输出要结构化中文 Markdown | 稳定偏好 |
| 工作日晚上通常只有约 1 小时可支配 | 稳定节奏（规范中明确列为应抽取） |
| 数据必须能本地保存，不接受把用户资料交给第三方 | 硬约束 |

**不放**

| 反例 | 违反的门槛 |
|------|------------|
| 「RAG 是检索增强生成」 | 与主人无关的常识 |
| 「本周要写 W33 周报」 | 阶段性任务 ≠ 稳定画像 |
| 「相对这个路线图我时间紧」写成「我每周都没空」 | 去语境泛化 |

## 11. 内容生产工艺

### 11.1 流程

1. **准备实例**：一台普通实例（`DEMO_MODE` 关闭），空 KB，配好 chat / embed 模型链与搜索 provider。
2. **前置资产**：`系统/戒律.md`、`系统/心法.md`、两个 Skill 包属于人工撰写的前置资产，不是跑出来的。由脚本第 0 步导入。
3. **剧本**：`demo/seed/script.yaml` 按会话顺序列出每轮用户消息、附件、`doc_context`、`web_enabled`、启用的 Skill。
4. **真跑**：`demo/seed/run.py` 依次 `POST /api/conversations` + `POST /api/chat`，消费 SSE 到 `done`，轮次间节流。
5. **人工定稿**：文档直接改磁盘上的 `.md`；会话用 dump/load 工具改。
6. **提交**：见 §11.3 的进 git 形态。
7. **构建**：`demo/build.py` 物化到运行时 KB 并重建索引。

### 11.2 会话与记忆的 dump / load 工具

文档好改，会话不好改——消息、turn 结构、工具调用事件都在 `.kb/conversations/conversations.db` 里，记忆事实在记忆库的 SQLite 里。手写 SQL 修一句措辞既痛苦又无法回退。

- `demo/tools/dump.py`：把 `conversations.db` 导成每会话一个 JSON，把记忆事实导成一个 JSON
- `demo/tools/load.py`：改完导回对应的 SQLite

副作用是好的：进 git 之后，会话与记忆都变成可 diff、可 review 的文本。

### 11.3 进 git 的形态

**SQLite 一律不进 git。** 进 git 的是三类纯文本：

```
demo/
  knowledge/          全部 Markdown 与附件（含 系统/、技能/），原样即定稿
  conversations/      每会话一个 JSON（dump.py 产出）
  memory.json         记忆事实（dump.py 产出）
  manifest.json       reference_date 等构建元数据
```

**绝不能提交**：

- `.kb/settings.json`（含明文 API Key）
- `.kb/auth.json`、`.kb/sessions.json`
- `conversations.db` 及任何 `*.db` / `*.db-wal` / `*.db-shm`
- `.kb/index/`（FTS / 向量，可重建）
- `*_cooldown.json`

演示站的管理员密码由部署环境单独设置，不随内容分发。仓库里加一条 CI 检查：`demo/` 下出现上述任一模式即失败。

对应地，`demo/build.py` 的物化顺序是：拷贝 `knowledge/` 到运行时 KB → `load.py` 灌入会话与记忆 → 平移时间戳 → 重建索引。

### 11.4 时间戳平移

`demo/manifest.json` 记录 `reference_date`（真跑定稿那天）。`demo/build.py` 计算 `offset = today - reference_date`，对会话消息与 turn 时间、文档元数据中的时间字段、记忆事实时间统一加 `offset`。

这样演示站永远看起来是「最近还在用」，而不是停在某个陈旧日期。

### 11.5 部署即重置

演示站容器启动时执行 `demo/build.py`：清空运行时 KB → 从 `demo/knowledge/` 物化 → 平移时间戳 → 重建索引。

「部署」与「重置」是同一条路径，不需要单独的重置逻辑；任何运行期漂移在下次重启自动消失。

## 12. 错误码约定

| HTTP | code | 场景 |
|------|------|------|
| 403 | `demo_read_only` | guest 触碰写接口，或带 `conversation_id` 聊天 |
| 403 | `demo_quota_exceeded` | 访客 / IP / 全站额度用尽 |
| 429 | `demo_busy` | 并发回合超限 |
| 401 | `auth_required` | 非 demo 模式下未登录（不变） |

## 13. 验证要点

**根因级测试（最重要的一条）**：遍历 `app.routes` 的全部路由，断言在 `DEMO_MODE` + guest 身份下，只有读白名单内的路由返回非 403。这样以后任何人新增路由，测试会直接提示「这个新接口在演示站默认是关的，确认要开吗」，而不是等出事再补用例。

其余：

- guest 发一条消息后：无新会话记录、无新文档、无新记忆事实、无 outbox 任务
- demo 工具目录中不含 §6.2 的移除项；`ToolRegistry.execute` 对这些名字硬拒
- `KnowledgeWriter` 在 demo 下任何写意图均抛错
- guest 读 `GET /api/admin/settings`：所有密钥字段为 `"***"`，不含任何真实片段；链式嵌套同样覆盖
- `GET /api/admin/export`、`GET /api/download-zip` 对 guest 返回 403
- `POST /api/auth/setup` 在 demo 下返回 403
- 带 `ephemeral_from` 聊天：能读到源会话上下文，且源会话消息数不变
- 访客 session 不写入 `.kb/sessions.json`
- 限流：超过单 session 阈值后返回 `demo_quota_exceeded`
- 管理员登录后不受任何 demo 限制
- `demo/build.py` 两次构建结果等价（除时间戳按当日平移外）

## 14. 实施顺序

两条可并行的线，各自一个实施计划。

**线 A：Demo 运行时**

1. `DEMO_MODE` + 身份解析 + 访客 session + `POST /api/auth/guest`
2. `DemoGuardMiddleware` 白名单 + 路由遍历测试 + 密钥二次遮蔽
3. Agent 三层防写 + 预览式写工具 + 时间线事件
4. `ephemeral_from`
5. 限流
6. 前端 `useDemoCapability` + 演示条 + 引导 + 403 兜底 + 预览卡渲染

先做 1-2 就已经安全可上线（只是没有 wow）；3-6 是体验增量。

**线 B：Demo 内容**

1. 前置资产撰写（系统层、两个 Skill 包）
2. 剧本 `script.yaml`
3. `run.py` 真跑 + 迭代定稿
4. dump/load 工具
5. `demo/` 内容提交 + CI 密钥检查
6. `build.py` + 时间戳平移

线 B 只需要一台普通实例，不依赖线 A。
