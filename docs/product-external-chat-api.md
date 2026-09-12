# 对外聊天 API（待确认）

> 状态：**待你确认**（2026-09-12）。按方案 A 收束：底层仍是同一套角色，入口只在设置 → API Key。尚未落地代码。确认后另写 ADR。
>
> 配套：[CONTEXT.md](../CONTEXT.md)、[product-multi-role.md](product-multi-role.md)、[ADR 2026-09-10 timeline](adr/2026-09-10-role-timeline.md)、[ADR 2026-09-10 sandbox](adr/2026-09-10-role-scoped-sandbox.md)。

## 0. 一句话

给自己的脚本开一把 Key，打 `POST /api/v1/chat` 跑现有 Agent（Skill + 只读知识库 + 沙箱）。这件事在底层就是**多一个普通角色**；这个角色不进左栏，只住在设置的 API Key 页。在那里配置它的人设，并用和其它角色同一套时间线/消息组件查看全部会话。

## 1. 已拍板（不再改，除非你推翻）

| 点 | 决定 |
|----|------|
| 谁调用 | 自己的脚本/自动化。低并发。不做多租户、限流、OAuth。 |
| 展示 | 不和日常聊天混。不进左栏角色列表，不进其它角色的时间线。 |
| KB / Skill | 可读、可跑 Skill；不能改文件、不能改启用集、不能写回知识库。 |
| 沙箱 | 能跑。因它是独立角色，自然是独立容器和卷，不和现有角色抢、不互相 interrupt。 |
| 角色 | **方案 A（本页收束）**：一个隐藏系统角色，同一套角色逻辑。 |
| 会话 | 默认每次调用新建一段并落库；可带 `conversation_id` 在 API 会话里多轮。不续网页 tip。 |
| 响应 | 同步 JSON；超时 202，可轮询。 |

## 2. 角色：同一套逻辑，换一个壳

现网角色同时管：人设、会话时间线、沙箱 slot、（可选）例行任务。API **不另造一套**，只加可见性：

| 字段 | API 角色 | 左栏角色 |
|------|----------|----------|
| 存储 | `roles` 表同一行，`id=__api__`，`visibility=hidden`（或 `kind=api`） | `visibility=sidebar`（缺省） |
| 人设 / 头像 / 名称 | 有，在设置 → API Key 编辑 | 右栏 / 角色设置 |
| 会话 | `conversations.role_id=__api__`，另标 `origin=api` | `origin=web` |
| 时间线 API | 仍是 `GET /api/roles/__api__/timeline` | 同形 |
| 沙箱 | `RoleSandboxPool.get("__api__")`，永不借用他人 | `get(role_id)` |
| 左栏 `GET /api/roles` | **过滤掉** | 只返回这些 |
| 例行任务 / 开场引导 | P0 不做（脚本自己触发） | 照旧 |
| 记忆抽取 | 不跑（脚本内容不是主人画像） | 照旧三道门槛 |

启动时若不存在则创建：名称默认「开放接口」，`onboarding_status=completed`，不可删、不可 `is_default`。

**多把 Key 共用这一个角色。** Key 只是凭证。人设、沙箱、历史都是这一份。P0 不做「每把 Key 一个隐藏角色」；真要隔离身份再加。

「在设置 API Key 的时候配置一个角色」= API Key 页**同时**就是这个隐藏角色的设置（名称/头像/人设），不是去下拉挑选左栏里某个聊天角色。

## 3. 界面：只出现在设置 → API Key

新设置页签 **「开放接口」**（或「API」）。这是该角色在产品里的唯一入口。

页里三块，自上而下：

1. **角色**  
   名称、头像、人设。控件复用现有角色设置字段，写入同一 `RoleStore`。这里就是「为 API 配置角色」。

2. **API Key**  
   创建（明文只显示一次）、名称、吊销、上次使用。`Authorization: Bearer lc_live_…`。可有多把，都打到 `__api__`。

3. **这个角色的聊天历史**  
   和主界面其它角色**同一套**能力：统一时间线（多段 + 分隔）、点开看消息正文、工具卡、沙箱日志。数据走现有 timeline / conversation 读取，只是壳在设置页里，不切左栏、不占中栏日常聊天。  
   P0 **只读**（查看历史和内容）。要接着聊，脚本再带 `conversation_id`。设置页不放输入框，避免和主界面两套 composer。

设置面板偏窄时：历史区在页签内滚动；需要看长对话时，点一段用与主界面相同的消息渲染（可全宽层）。**不要**为此把左栏选中切到 `__api__`。

左栏角色列表、角色搜索、忙碌角标、最近活动：**当这个角色不存在**。Ctrl+K 工作区搜索默认不含它的会话。

## 4. 沙箱：还是「一角色一把」

不新发明 slot 类型。隔离来自「它是另一个 `role_id`」：

- 卷：`lorechat-sandbox-ws-api`，不复用默认角色的 `lorechat-sandbox-workspace`
- cwd：`/workspace/conversations/{conversation_id}`（现网约定）
- stop API 回合只 interrupt `__api__`；停左栏某角色不影响它
- 四个聊天角色都占着沙箱时，API 仍能跑：`sandbox_max_roles` **只数左栏角色**，`__api__` 另留 1 个活容器（低并发够用）。空闲 TTL 同样可回收容器、留卷
- 脚本等不了网页点确认：`origin=api` 跳过 `SandboxCommandGate`，直接执行
- 能 `sandbox_run` / `stage_to_sandbox` / 读列目录；**不能** `publish_from_sandbox`

## 5. 能力边界（硬门在工具层）

`select_tools(mode=api)`（或等价 allowlist），不要靠提示词黑名单：

- 有：`search_kb`、`read_doc`、`list_kb_structure`、`read_conversation_context`、`fetch_url`、`recall_memory`、沙箱执行与读、可选 `web_search`
- 无：`write_doc` / `edit_doc` / `write_kb_file` / `update_doc_meta` / `summarize_conversation` / `move_entry` / `delete_kb` / `publish_from_sandbox` / `manage_memory` / 角色与例行任务全部工具

Skill：catalog =（Key 可选白名单，否则全局启用集）∩ 请求里的 `skills`。只读包内 `SKILL.md`，不能改启用集。交集空 → 400。

## 6. 会话

- 不传 id：`conversations.create(role_id=__api__, origin=api)`，跑一轮，返回 `conversation_id`
- 带 `conversation_id`：必须是这个角色、`origin=api`、这把 Key 创建的，否则 404
- 同时一个 running turn；冲突 409
- P1 才做调用方 `thread_id` 映射
- `ensure_active` / 连续窗口 / 「新话题」只看 `origin=web`，API 更新时间戳也抢不走主人 tip

## 7. HTTP

脚本（Bearer）前缀 `/api/v1`：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/chat` | 见下 |
| GET | `/api/v1/conversations` | 本 Key 的会话 |
| GET | `/api/v1/conversations/{id}` | 消息 |
| GET | `/api/v1/conversations/{id}/turns/{turn_id}` | 回合 |
| POST | `/api/v1/conversations/{id}/stop` | 停，只打 `__api__` 沙箱 |
| GET | `/api/v1/skills` | 可用 catalog |

网页（Cookie）继续用现有 `/api/roles/{id}`、`/api/conversations/{id}` 读 `__api__` 的历史；另加 Key CRUD（如 `/api/open-api/keys`）。`GET /api/roles` 默认不含 hidden。Bearer 不能打设置/KB 树；Cookie 不能当 v1 凭证。

`POST /api/v1/chat`：

```json
{
  "message": "用周报助手整理：…",
  "conversation_id": null,
  "skills": ["技能/周报助手"],
  "title": "2026-W37 周报",
  "wait": true,
  "timeout_sec": 120
}
```

```json
{
  "conversation_id": "a1b2c3d4e5f6",
  "turn_id": "…",
  "status": "completed",
  "message": { "id": "…", "role": "assistant", "content": "…" }
}
```

`status`：`completed` \| `running` \| `needs_input` \| `failed` \| `stopped`。超时 202。Agent 若 `ask_user`，设置页历史里能看到征询；P1 再在该页回答。沙箱已跳过确认，pending 会少。

```bash
curl -sS "$LORECHAT/api/v1/chat" \
  -H "Authorization: Bearer lc_live_…" \
  -H "Content-Type: application/json" \
  -d '{"message":"把这段会议记录写成纪要：…","skills":["技能/会议纪要"]}'
```

## 8. 存储与 seam

- `roles`：`visibility`（`sidebar` \| `hidden`），缺省 `sidebar`；确保 `__api__` 行
- `conversations`：`origin` 缺省 `web`；`api_key_id`；tip/timeline/左栏活动排除 `origin=api` 与 `visibility=hidden`
- Key：`{kb}/.kb/api_keys.json`，只存哈希与前缀
- `RoleSandboxPool`：`max_roles` 统计排除 hidden；`SandboxTools` 仍只按 `conversation.role_id` 取 slot（API 会话的 role_id 就是 `__api__`，不会撞上通用）

HTTP 薄路由 + `PublicChatService`（组 catalog、`mode=api`、`begin_persisted_turn`、等到结束）。不解析内部 SSE；不改 `chat_routes.py` 加 header 冒充外开。

## 9. 分期

**P0**：Key；`POST /api/v1/chat` + 轮询/stop；隐藏角色确保存在；设置页三块（角色 / Key / 只读时间线）；`mode=api` 工具集；专用沙箱且不占 4 角色名额；跳过沙箱网页确认。

**P1**：`thread_id`；精简 SSE；设置页回答 `needs_input`。

**P2**：OpenAI 兼容适配；用量；附件。

## 10. 验收

1. 左栏始终没有「开放接口」；选任何左栏角色，时间线里没有 API 段。
2. 设置 → API Key 能改这个角色的人设，能看到它全部会话正文和工具/沙箱日志。
3. 两把 Key 都打到同一角色；历史在同一时间线，可用 `api_key_id` 区分来源（徽章即可）。
4. API 沙箱与某左栏角色沙箱同时跑；一方 stop 不影响另一方。
5. 四个左栏角色沙箱占满时，API 仍能启动自己的容器。
6. 模型调不到写库 / 回写 / 改 Skill / 改角色的工具。
7. 无 Key → 401；网页连续窗口不被 API 打乱。

## 11. 明确不做

- API 挂到「通用」或任一左栏角色
- 左栏多一个可切换的聊天角色
- 每把 Key 一把隐藏角色（P0）
- 设置页再做一个和第二套聊天引擎
- 设置页给这个角色开网页输入框（P0）
- ephemeral、自动写回 KB、另写记忆抽取提示词
