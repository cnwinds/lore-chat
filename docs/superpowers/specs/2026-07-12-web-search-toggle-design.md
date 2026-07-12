# 联网搜索开关（web_search 能力显式化）

日期：2026-07-12  
状态：设计中  
前置文档：[2026-07-10-agent-tools-design.md](./2026-07-10-agent-tools-design.md)、[2026-07-12-architecture-fixes.md](../plans/2026-07-12-architecture-fixes.md)

## 1. 问题

### 1.1 现状

"要不要出网"目前完全由 Agent **隐式**决定：

- `web_search`（助手主动搜索引擎）与 `fetch_url`（抓取用户贴的链接）在每一轮都作为工具**无条件**下发给模型，模型自行判断是否调用。
- 用户无法控制某次问答"只用本地知识库"还是"允许联网"，带来成本、隐私、可预测性问题。

这也是 `/ingest`、`/ask` 端点重构长期悬而未决的根因——因为"抓 URL / 联网搜索"能力糊在 Agent 内部说不清，端点该不该保留 Agent 无从判断（见 architecture-fixes「不在本计划内」表）。

### 1.2 `mode` 是软约束，不是真开关

`AgentOrchestrator.run()` 每轮都无条件传全量 `TOOL_DEFINITIONS`：

```python
stream_iter = iter(self.llm.stream_chat_with_tools(messages, TOOL_DEFINITIONS, big=True))
```

`mode`（`default`/`force_write`/`no_write`）仅通过 system prompt 文字提示生效（`build_system_prompt` 加一句"本轮禁止调用 write_kb"）。即**当前所有模式约束都靠模型自觉**，`no_write` 时 `write_kb` 其实仍在工具列表中——这是一个已存在的隐患。

## 2. 目标

1. 在聊天界面提供**「联网搜索」开关**，把"是否允许主动联网搜索"的决策权显式交给用户。
2. 关闭时：仅用本地知识库（`search_kb`/`read_doc`）+ 用户贴的链接（`fetch_url`）作答；助手**不主动**发起 `web_search`。
3. 打开时：本地优先、联网补充——先查本地，本地不足或用户要时效信息时再 `web_search`。
4. 约束以**硬门**实现：按开关过滤下发给模型的工具列表，而非仅靠 prompt。顺带把 `mode` 也改为硬门过滤，消除既有隐患。

## 3. 非目标

- **不动 `/ingest`、`/ask` 端点的去留**：本次只把"联网"抽象为正交能力；端点重构留待后续单独决策（届时耦合已解除）。
- **不做联网结果与本地结果的复杂排序/打分融合**：沿用现有 prompt 的"先本地、后联网补充"精神，不引入新的融合算法。
- **不改 `fetch_url` 语义**：贴链接=显式意图，始终允许，不受开关影响。
- 不做三态（关/自动/强制）；采用布尔开关，消除"自动"的模糊性。

## 4. 决策记录

| 项 | 决策 |
|----|------|
| 开关粒度 | **布尔**（开/关），不做三态 |
| 开关语义 | 只控制 `web_search`（主动联网搜索）；`fetch_url` 始终允许 |
| 开关文案 | **「联网搜索」**（非"联网"，避免与贴链接读取混淆） |
| 默认值 | **默认关**（与"本地知识库助手"定位一致，联网是增强项） |
| 作用域 | **每次请求传参**，前端 localStorage 记住上次选择 |
| 融合策略 | 先查本地，本地不足或需时效信息时再联网补充（不强制每轮都搜） |
| 实现方式 | **硬门**：按 `web_enabled` 过滤 `TOOL_DEFINITIONS`；`mode` 一并改硬门 |
| 抽象维度 | `web_enabled` 与 `mode` **正交**，不折叠进 `mode` |
| 端点重构 | 本次不做 |

## 5. 方案

### 5.1 能力过滤（后端核心）

在 orchestrator 内引入统一的"可用工具集"计算，作为唯一的工具门禁：

- 入参：`mode`、`web_enabled`。
- 规则：
  - `web_enabled=False` → 从工具集移除 `web_search`（保留 `fetch_url`）。
  - `mode=no_write` → 移除 `write_kb`（顺带修复既有软约束隐患）。
  - `mode=force_write` → 保留全部（prompt 仍强制 `write_kb`）。
- 过滤后的工具列表传给 `stream_chat_with_tools`，取代当前无条件的 `TOOL_DEFINITIONS`。

```
可用工具 = TOOL_DEFINITIONS
  - (web_search      if not web_enabled)
  - (write_kb        if mode == no_write)
```

### 5.2 signature 透传

- `AgentOrchestrator.run(..., web_enabled: bool = False)` 新增关键字参数（默认关，与产品默认一致）。
- `ChatBody` 新增 `web_enabled: bool = False`；`/chat` 透传到 `run()`。
- `/ask`、`/ingest` 暂不加该参数（保持现状；端点重构时再定）。

### 5.3 Prompt 调整

`prompts.py`：

- 联网**关**时追加提示：本轮无联网搜索能力；若本地知识库无依据，明确告知用户"本地未找到，可开启联网搜索后重试"，**不得假装搜过或凭记忆补全**。
- 联网**开**时沿用现有"检索优先级"：先 `search_kb`，本地不足或用户要时效信息时再 `web_search`；不强制每轮都搜。
- `web_search` 从工具列表移除后，模型不会看到该工具定义，prompt 提示作为语气兜底。

### 5.4 前端

- `Chat.tsx`：输入框旁增加「联网搜索」开关（如小地球/闪电图标 + 文案），默认关；状态存 localStorage。
- `api.ts`：`chatStream` 请求体带上 `web_enabled`。
- 开关状态在会话内可见，切换即时生效（作用于下一条消息）。

## 6. 实现范围

| 位置 | 改动 |
|------|------|
| `app/engine/agent/orchestrator.py` | `run()` 加 `web_enabled`；新增可用工具集过滤，替换无条件 `TOOL_DEFINITIONS` 下发 |
| `app/engine/agent/tools.py` | 提供工具过滤辅助（如 `select_tools(mode, web_enabled)`），或在 orchestrator 内实现 |
| `app/engine/agent/prompts.py` | 联网关/开的提示分支；`build_system_prompt` 增 `web_enabled` 影响的语气兜底 |
| `app/api/routes.py` | `ChatBody` 加 `web_enabled: bool = False`；`/chat` 透传 |
| `frontend/src/api.ts` | `chatStream` 请求体带 `web_enabled` |
| `frontend/src/components/Chat.tsx` | 「联网搜索」开关 UI + localStorage 记忆 |
| `frontend/src/index.css` | 开关样式 |
| `backend/tests/test_agent_orchestrator.py` | 关时工具集不含 `web_search`、含 `fetch_url`；`no_write` 时不含 `write_kb` |
| `backend/tests/test_api.py` | `/chat` 传 `web_enabled=false` 不触发 `web_search`；默认关 |

## 7. 验收

- **默认关**：不带 `web_enabled` 的 `/chat` 请求，工具集不含 `web_search`；模型无法主动联网搜索。
- **关闭时**：贴链接仍能 `fetch_url`；本地无依据时如实告知"可开启联网搜索"，不编造。
- **打开时**：`web_enabled=true` 后 `web_search` 重新可用；先本地后联网补充。
- **硬门生效**：`no_write` 模式下工具集不含 `write_kb`（修复既有软约束隐患）。
- **前端**：开关默认关、切换后下一条消息生效、刷新后保留上次选择。
- **正交性**：`mode` 与 `web_enabled` 组合互不干扰（default/force_write/no_write × 开/关）。
- **无回归**：既有 `/chat`、`/ingest`、`/ask` 测试通过。

## 8. 对端点重构的后续影响（备忘，非本次范围）

"联网"显式化后，端点关系变为 `mode × web_enabled × 响应形态`，耦合解除：

- `/ask` ≈ `/chat`（`no_write` + web 用户选 + 同步）→ 后续可评估废弃或定位为"机器同步 API"。
- `/ingest` 纯文本可直连 organizer；含 URL 时才需 Agent（`fetch_url`）→ 可干净拆快路径。

这些留待独立的端点重构计划，本 spec 只负责解除耦合。
