# 多角色产品设计（ADR 配套 + Grok Bot 三栏布局）

> 权威决策见 [ADR 2026-09-09](adr/2026-09-09-multi-role-shell.md)、[ADR 2026-09-10 always-visible](adr/2026-09-10-multi-role-always-visible.md)、[ADR 2026-09-10 timeline](adr/2026-09-10-role-timeline.md)。本文展开产品/界面/分期,供实现对照。

## 0. 角色列表始终可见（2026-09-10 更新）

**最新决策**：左侧角色列表**始终显示**，即使只有一个角色。

**理由**：
- 保持 UI 一致性，用户不会因角色数量变化而困惑于界面布局的突然改变
- 提供清晰的「当前活跃角色」视觉指示
- 简化实现：无需维护条件显示逻辑
- 符合 Grok Bot 的 UX 参考

**废弃规则**：~~早期设计（ADR 2026-09-09 §2）曾考虑「单角色时隐藏角色列表，多角色时显示」，现已被明确废弃。~~ 详见 [ADR 2026-09-10](adr/2026-09-10-multi-role-always-visible.md)。

## 0.1 角色统一时间线（2026-09-10）

**最新决策**：选中角色后，中栏展示该角色**全部会话段**拼成一条时间线（段间分隔），而非只加载空 tip。详见 [ADR 2026-09-10 timeline](adr/2026-09-10-role-timeline.md)。

**废弃规则**：~~主区只看活跃线、历史主要靠抽屉~~。

## 1. 产品模型

| 维度 | 约定 |
|------|------|
| 角色 | 可多个；字段：名称、头像、系统提示词、定时任务（定时后续） |
| 默认 | 启动仅一个「通用」默认角色（`id=default`） |
| 知识库 | **全角色共享**读写 |
| 记忆 | **全局抽取**覆盖所有角色会话；规则仍为关于主人 / 耐久性 / 语境保全；**关段**亦触发抽取 |
| 并行 | 角色独立上下文与 turn；切换 UI **不取消**其他角色 running turn |
| 生长 | 用户可创建新角色（设置 / 后续对话工具）；不强制安装向导 |

心法/戒律 = 全局底线；角色 `system_prompt` = 叠加层。

## 2. 三栏布局（Grok Bot 参考）

从左到右：

1. **左栏（固定）**
   - **上半部分**：角色列表（始终可见）
     - 本角色会话搜索（命中滚动定位）
     - ＋新建角色
     - 角色卡片列表（头像、名称、人设预览；右侧为最近会话活动：当天时刻 / 昨天 / 周几 / 日期）
     - 活跃角色高亮显示
   - **下半部分**：知识库树
     - 与原有 KB 树交互保持一致
     - 保留所有拖放、重命名、下载等功能

2. **中栏（弹性）**
   - 角色统一时间线（多段 + 分隔）+ tip composer
   - 对话段归属于角色

3. **右栏（可折叠）**
   - 展开：顶栏齿轮（名称/头像/人设）+ 收起；中部角色形象卡（头像或色块，**不是**虚拟机屏幕）；底部例行任务说明与「创建例行任务」
   - 收起：右栏完全隐藏，中栏顶栏出现展开按钮
   - 字段仍是名称、头像、人设、例行任务（每天/工作日/每周/每月时刻，或间隔 / cron；北京时间）

### 无虚拟机 / 桌面屏幕

Grok Bot 参考截图中的「连接中 / 屏幕」大块不在 lore-chat 的产品范围内。**严格不实现任何 VM / 桌面显示 UI**。

### 对话与角色关联（统一时间线）

- 每条会话段（`conversation`）归属于一个角色；**不**把多段物理合并成一行。
- 选中角色 → 中栏展示该角色**全部段**拼成一条时间线（旧上新下），段间有分隔线。
- 可输入/发送的只有当前 tip 段；更早段只读，搜索命中则滚动定位。
- Agent `history` **仅当前 tip 段**；跨段靠默认检索 / `search_kb`，不自动拼接。
- 「新话题」= 强制新开一段；超时超出 `continuity_idle_hours` 也会静默新段。
- 关段（窗口外新建 / 新话题）时对上一有内容段触发记忆抽取。

## 3. 数据与 API（实现清单）

### 3.1 存储

- `{kb}/.kb/roles/roles.db` → `roles` 表  
  - `id, name, avatar, system_prompt, is_default, sort_order, onboarding_status, created_at, updated_at`
  - `onboarding_status`: `none` | `active` | `completed` | `skipped`
- `conversations.role_id`（缺列 `ALTER` + 默认 `default`；旧会话回填）
- 配置：`Settings.continuity_idle_hours: float = 6.0`

### 3.2 活跃 tip 算法

对给定 `role_id`（决定**可写 tip**，不是「只展示这一段」）：

1. 优先复用该角色下最新且 `message_count == 0` 的会话；
2. 否则取该角色最新会话：若 `last_user_message_at`（无则 `updated_at`）在连续窗口内 → 用之；
3. 否则创建新会话；并对被顶替的上一 tip（有消息时）`request_immediate` 记忆抽取。

### 3.3 Agent 工具（角色配置的主要接口）

**产品设计修正（2026-09-10）**：角色配置（名称、头像、人设、定时任务）的**主要接口**是 **LLM Agent 工具**，而非外部 HTTP API。

HTTP `/api/roles*` 保留用于 UI shell（列表、ensure-active、可选右栏快捷操作），但文档与目录中明确：**Agent 通过工具调用变更配置**。

#### Agent 工具列表

| 工具名 | 说明 |
|------|------|
| `create_role` | 创建新角色 `{name, system_prompt?, avatar?}` |
| `update_role` | 更新角色属性 `{role_id?, name?, avatar?, system_prompt?}`；默认当前会话角色 |
| `list_role_schedules` | 列出角色定时任务 `{role_id?}` |
| `create_role_schedule` | 创建例行任务 `{role_id?, prompt, timing?, interval_hours?, enabled?}` |
| `update_role_schedule` | 更新例行任务 `{schedule_id, prompt?, timing?, interval_hours?, enabled?}` |
| `delete_role_schedule` | 删除定时任务 `{schedule_id}` |
例行任务 `timing.kind`：`interval`（间隔小时）/ `hourly` / `daily` / `weekdays` / `weekly` / `monthly` / `cron`。日历时刻按**北京时间**。旧客户端仍可只传 `interval_hours`。

#### 角色引导流程

新角色创建时，`onboarding_status` 默认为 `active`（有 system_prompt 则为 `completed`）。

当 `onboarding_status=active` 时，创建并切换到该角色后，系统用隐藏触发回合让角色**先开口**（不空等主人先说话），并注入引导提示层：
- 简短自我介绍，每次只问一个问题
- 了解职责、输出、边界、风格
- 询问是否需要定时任务
- 整理人设草案 → 展示 → 确认 → `finalize_role_onboarding`（写入角色设置中的人设）

用户可选择跳过引导（设置 `onboarding_status=skipped`）。已写人设（创建时带 `system_prompt`）则直接 `completed`，不发起引导。

### 3.4 HTTP（UI Shell 用）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/roles` | 列表（启动确保默认角色） |
| POST | `/api/roles` | 创建（UI 可调；Agent 优先用工具） |
| GET/PATCH/DELETE | `/api/roles/{id}` | 读/改；默认角色不可删；右栏快捷入口 |
| POST | `/api/roles/{id}/ensure-active` | 解析/创建 tip → `{conversation_id, created}` |
| GET | `/api/roles/{id}/timeline` | 角色统一时间线（段列表 + 消息；含 tip） |
| POST | `/api/roles/{id}/new-topic` | 强制新话题（关段抽取 + 新空段） |
| GET | `/api/roles/busy` | 有 running turn 的 `role_ids` |
| GET/POST | `/api/roles/{id}/schedules` | 角色定时列表 / 创建 |
| PATCH/DELETE | `/api/roles/{id}/schedules/{sid}` | 改启停与定时规格 / 删除 |
| POST | `/api/conversations` | body 可选 `{role_id, title}`；缺省绑默认角色 |
| GET | `/api/conversations?role_id=` | 可选按角色过滤 |
| GET | `/api/conversations/search` | 会话全文搜索，可选按角色过滤 |

### 3.4 Agent 注入

顺序：心法戒律 →（可选）角色 system_prompt 块 → 内置 SYSTEM_PROMPT → user_memory → …  
新 tip 首轮另注入「检索摘要」（本角色会话 + KB）。

在 `TurnExecutionHub` / `AgentOrchestrator.run` 按 `conversation.role_id` 查 `RoleStore`。

## 4. 前端实现要点

| 模块 | 改动 |
|------|------|
| [`AppShell.tsx`](../frontend/src/components/app/AppShell.tsx) | 三栏布局容器：左（角色列表 + KB）、中（Chat）、右（RoleConfigPanel） |
| [`RoleList.tsx`](../frontend/src/components/role/RoleList.tsx) | 角色列表：始终可见；角色内搜索定位；「新话题」 |
| [`RoleConfigPanel.tsx`](../frontend/src/components/role/RoleConfigPanel.tsx) | 右侧角色配置面板 |
| [`ChatMessageList.tsx`](../frontend/src/components/chat/ChatMessageList.tsx) | 多段时间线 + 段间分隔 |
| [`useRoleTimeline.ts`](../frontend/src/hooks/chat/useRoleTimeline.ts) | 加载角色 timeline |
| [`api.ts`](../frontend/src/api.ts) | Role / timeline API |

## 5. 交互流程

### 新建角色
1. 点击角色列表顶部「＋」按钮
2. 创建角色并自动切换
3. 若未预填人设，中栏由角色主动开口，一次一问了解职责与协作方式
4. 主人确认草案后，角色调用 `finalize_role_onboarding` 写入设置中的人设（也可随时在右侧面板改）

### 切换角色
1. 点击角色列表中的角色卡片
2. 调用 `/api/roles/{id}/timeline`（内含 ensure tip）
3. 中栏展示该角色整条时间线；composer 绑定 tip
4. 右侧配置面板加载该角色信息

### 新话题
1. 点击「新话题」→ `POST .../new-topic`
2. 时间线底部出现新空段与分隔线；上一 tip 进入只读并触发记忆抽取

### 编辑角色配置
1. 在右侧面板修改字段并保存
2. 刷新角色列表显示

### 定时任务
- 右侧面板「定时任务」区域 CRUD

## 6. 分期

1. **P0** — RoleStore + `role_id` + API + 默认角色；创建/列表会话带角色；prompt 注入；侧栏始终显示角色列表与活跃线；三栏布局。
2. **P1** — 连续窗口精细化、用户侧会话搜索、新话题文案与空态引导。（含设置页连续窗口、手机角色 sheet、提示词「接着上次」强化）
3. **P2** — 角色设置页（人设/头像）、定时任务 CRUD、对话创建角色、忙碌角标、本角色历史抽屉。

## 7. 验收

### P0

- 启动打开：角色列表可见，显示默认角色；可直接聊，会话挂在默认角色。
- 创建第二角色后：角色列表更新；切换换活跃线；后台另一角色 turn 不被 cancel。
- KB / 记忆仍全局；角色提示词进入 system（有角色文案时）。
- 旧库升级：已有会话 `role_id=default`，出现默认角色行。
- 三栏布局：左侧角色列表 + KB 树，中间 Chat，右侧 RoleConfigPanel。

### P1

- 设置 → Agent 可改连续窗口小时数；`ensure-active` 使用该值。
- 侧栏可搜索历史对话，点选跳转会话（及消息）。
- 空态有简短引导（直接说 / 搜索 / 接着上次 / 建角色）。
- 用户说「接着上次 / 我们说过」时，system 要求先搜会话再答。

### P2

- 角色设置：可改名称、头像 URL、人设；非默认角色可删（会话迁回默认）。
- 角色级定时：设置页可增删启停；到期写入该角色活跃线；有 running turn 时顺延。
- Agent 工具 `create_role`：对话中可创建角色，侧栏随后可见。
- 忙碌角标（该角色有 running turn）。
- 本角色会话历史抽屉。

## 参考

- Grok Bot UI 截图：`/workspace/lore-ui/grok-bot-reference.png`
- ADR：`docs/adr/2026-09-09-multi-role-shell.md`、`docs/adr/2026-09-10-multi-role-always-visible.md`
