# 侧边栏新建会话实时显示

日期：2026-07-11  
状态：待实现

## 问题

点击「新建」只清空本地 `activeConversationId`，会话要等发出第一条消息才 `POST /api/conversations`。侧边栏因此不会立刻出现新条目；标题也要等流式结束后 `append_exchange` 才更新。

## 目标

1. 点击「新建」后，侧边栏立刻出现并高亮该会话（标题「新对话」）。
2. 若当前已是空会话（`message_count === 0`），再点「新建」复用它，不重复创建。
3. 用户发出第一条问题后，侧边栏标题立刻变为问题摘要；流结束后再与服务端对齐。

## 非目标

- 不改后端会话存储结构。
- 不新增「获取或创建空会话」专用 API。
- 不自动清理历史空会话（仅避免新建时重复创建）。

## 方案（前端主导）

### 1. 新建 / 复用

`App.newChat` 改为异步：

1. 用当前侧边栏已知的会话列表（或先 `listConversations`）查找：`message_count === 0` 的会话。
2. 若存在：`setActiveConversationId(emptyId)`，必要时 `refreshSidebar`。
3. 若不存在：`createConversation()` → `setActiveConversationId(id)` → `refreshSidebar()`。

空会话判定以服务端列表为准；若当前已选中某空会话，直接保持即可。

### 2. 首问更新标题（乐观）

- 在 `Chat` 发消息时：若该会话尚无用户消息（本地 `msgs` 中无 `role === "user"`，或侧边栏 `message_count === 0`），调用回调把标题乐观设为问题首行截断（与后端 `_title_from_text` 一致：首行、最长 40 字 + `…`）。
- `Sidebar` 支持本地覆盖标题（`titleOverrides` 或由 `App` 下发更新后的列表项），立即重渲染。
- 流式 `done` 时现有 `onSidebarRefresh` 拉全量列表，清除覆盖，与后端标题、`message_count` 对齐。

后端仍在 `append_exchange` 时写标题；无需新接口。

### 3. 与现有懒创建的关系

- 「新建」已创建会话后，`Chat.ensureConversationId` 直接使用已有 `conversationId`，不再二次创建。
- 上传附件等仍走 `ensureConversationId`：若用户未点新建、直接上传，行为与现在一致（懒创建 + `onConversationCreated`）。

## 涉及文件

- `frontend/src/App.tsx` — `newChat` 创建/复用；标题覆盖状态；传给 Sidebar/Chat
- `frontend/src/components/Sidebar.tsx` — 展示覆盖标题（若由 App 合并进列表则可不动展示逻辑）
- `frontend/src/components/Chat.tsx` — 首问时通知标题更新
- 可选：抽 `titleFromText` 小工具与后端规则对齐

## 验收

1. 点「新建」→ 侧边栏立即出现「新对话」并高亮。
2. 再点「新建」（未发消息）→ 仍是同一条，不新增。
3. 发出首问 → 标题立刻变为问题摘要。
4. 回答结束后 → 标题与条数与服务端一致。
5. 从历史会话切回再新建 → 正常创建新空会话（若无其他空会话）。
