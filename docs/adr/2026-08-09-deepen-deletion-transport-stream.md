# ADR 2026-08-09：删除 / 消息图 / HTTP 传输 / 流投影

## 状态

已采纳（2026-08-09）

## 背景

Transcript / Archive / Schedule 落地后仍余：会话删除与消息图堆在 Store；`api.ts` 传输未拆；`useAgentStream` 把 reduce 缠在 hook；工具 progress 与 Organizer 征询深度内嵌。

## 决策

1. **`ConversationDeletionWorkflow`**：ledger → purge → 索引清理；Store 委托。
2. **`ConversationMessageGraph`**：append / inject / `mark_question_resolved`（含 `patch_timeline_choice_resolved`）。
3. **`httpTransport`**：`openJson` / `openSse` / `readSseResponse`；领域 endpoint 只拼 path/body。
4. **`agentStreamProjection`**：`reduceStreamEvent` + `shouldReloadConversation`；hook 接线。
5. **`ToolProgressExecutor`**：progress/cancel/duration seam。
6. **`AgentChoiceResolution`**：选项 → `IngestResult`；Organizer 薄委托。

## 后果

- 删除与征询可单测；SSE 传输可替换；流投影不依赖 React。
