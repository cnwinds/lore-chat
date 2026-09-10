# 多角色产品设计（ADR 配套 + Grok Bot 三栏布局）

> 权威决策见 [ADR 2026-09-09](adr/2026-09-09-multi-role-shell.md) 及 [ADR 2026-09-10](adr/2026-09-10-multi-role-always-visible.md)。本文展开产品/界面/分期,供实现对照。

## 0. 角色列表始终可见（2026-09-10 更新）

**最新决策**：左侧角色列表**始终显示**，即使只有一个角色。

**理由**：
- 保持 UI 一致性，用户不会因角色数量变化而困惑于界面布局的突然改变
- 提供清晰的「当前活跃角色」视觉指示
- 简化实现：无需维护条件显示逻辑
- 符合 Grok Bot 的 UX 参考

**废弃规则**：~~早期设计（ADR 2026-09-09 §2）曾考虑「单角色时隐藏角色列表，多角色时显示」，现已被明确废弃。~~ 详见 [ADR 2026-09-10](adr/2026-09-10-multi-role-always-visible.md)。

## 1. 产品模型

| 维度 | 约定 |
|------|------|
| 角色 | 可多个；字段：名称、头像、系统提示词、定时任务（定时后续） |
| 默认 | 启动仅一个「通用」默认角色（`id=default`） |
| 知识库 | **全角色共享**读写 |
| 记忆 | **全局抽取**覆盖所有角色会话；规则仍为关于主人 / 耐久性 / 语境保全 |
| 并行 | 角色独立上下文与 turn；切换 UI **不取消**其他角色 running turn |
| 生长 | 用户可创建新角色（设置 / 后续对话工具）；不强制安装向导 |

心法/戒律 = 全局底线；角色 `system_prompt` = 叠加层。

## 2. 三栏布局（Grok Bot 参考）

从左到右：

1. **左栏（固定）**
   - **上半部分**：角色列表（始终可见）
     - 搜索框（占位，暂未实现）
     - ＋新建角色按钮
     - 角色卡片列表（头像、名称、人设预览、更新时间）
     - 活跃角色高亮显示
   - **下半部分**：知识库树
     - 与原有 KB 树交互保持一致
     - 保留所有拖放、重命名、下载等功能

2. **中栏（弹性）**
   - 聊天区域（Chat 组件）
   - 保持现有对话交互不变
   - 对话归属于角色

3. **右栏（可折叠）**
   - 角色配置面板（RoleConfigPanel）
   - 字段：
     - 名称
     - 头像 URL
     - 人设（system_prompt）
     - 定时任务列表（interval_hours + prompt）
   - 折叠按钮（›/‹）

### 无虚拟机 / 桌面屏幕

Grok Bot 参考截图中的「连接中 / 屏幕」大块不在 lore-chat 的产品范围内。**严格不实现任何 VM / 桌面显示 UI**。

### 对话与角色关联

- 每条对话归属于一个角色
- 切换角色时，显示该角色的历史对话（活跃线）
- 新建对话在当前活跃角色下创建

## 3. 数据与 API（实现清单）

### 3.1 存储

- `{kb}/.kb/roles/roles.db` → `roles` 表  
  - `id, name, avatar, system_prompt, is_default, sort_order, created_at, updated_at`
- `conversations.role_id`（缺列 `ALTER` + 默认 `default`；旧会话回填）
- 配置：`Settings.continuity_idle_hours: float = 6.0`

### 3.2 活跃线算法

对给定 `role_id`：

1. 优先复用该角色下 `message_count == 0` 的会话；
2. 否则取该角色 `updated_at` 最新会话：若 `last_user_message_at`（无则 `updated_at`）在连续窗口内 → 用之；
3. 否则创建新会话并返回。

### 3.3 HTTP（建议）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/roles` | 列表（启动确保默认角色） |
| POST | `/api/roles` | 创建 `{name, system_prompt?, avatar?}` |
| GET/PATCH/DELETE | `/api/roles/{id}` | 读/改；默认角色不可删 |
| POST | `/api/roles/{id}/ensure-active` | 解析/创建活跃线 → `{conversation_id, created}` |
| GET | `/api/roles/busy` | 有 running turn 的 `role_ids` |
| GET/POST | `/api/roles/{id}/schedules` | 角色定时列表 / 创建 |
| PATCH/DELETE | `/api/roles/{id}/schedules/{sid}` | 改启停与间隔 / 删除 |
| POST | `/api/conversations` | body 可选 `{role_id, title}`；缺省绑默认角色 |
| GET | `/api/conversations?role_id=` | 可选按角色过滤（次级历史用） |
| GET | `/api/conversations/search` | 会话全文搜索，可选按角色过滤 |

### 3.4 Agent 注入

顺序：心法戒律 →（可选）角色 system_prompt 块 → 内置 SYSTEM_PROMPT → user_memory → …

在 `TurnExecutionHub` / `AgentOrchestrator.run` 按 `conversation.role_id` 查 `RoleStore`。

## 4. 前端实现要点

| 模块 | 改动 |
|------|------|
| [`AppShell.tsx`](../frontend/src/components/AppShell.tsx) | 三栏布局容器：左（角色列表 + KB）、中（Chat）、右（RoleConfigPanel） |
| [`RoleList.tsx`](../frontend/src/components/RoleList.tsx) | 角色列表组件：始终可见，显示所有角色，高亮当前活跃角色 |
| [`RoleConfigPanel.tsx`](../frontend/src/components/RoleConfigPanel.tsx) | 右侧角色配置面板：名称、头像、人设、定时任务 CRUD |
| [`KbSidebar.tsx`](../frontend/src/components/KbSidebar.tsx) | 左侧知识库树（原 Sidebar 的 KB 部分） |
| [`useRoleShell.ts`](../frontend/src/hooks/app/useRoleShell.ts) | 角色状态管理 hook：activeRoleId、切换角色、ensure-active、localStorage 持久化 |
| [`api.ts`](../frontend/src/api.ts) | Role API 函数与类型定义 |

## 5. 交互流程

### 新建角色
1. 点击角色列表顶部「＋」按钮
2. 创建默认角色（`新角色 <timestamp>`）
3. 自动切换到新角色
4. 在右侧配置面板编辑名称、头像、人设

### 切换角色
1. 点击角色列表中的角色卡片
2. 调用 `/api/roles/{id}/ensure-active` 解析或创建活跃会话
3. 右侧配置面板加载该角色信息
4. 中间聊天区加载该角色的活跃会话

### 编辑角色配置
1. 在右侧面板修改字段
2. 点击「保存」按钮
3. 通过 API 更新角色
4. 刷新角色列表显示

### 定时任务
- 右侧面板「定时任务」区域显示当前角色的所有定时任务
- 显示 interval_hours、prompt、启用状态
- 支持添加/编辑/删除定时任务

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
