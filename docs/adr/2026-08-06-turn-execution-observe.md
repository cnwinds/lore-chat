# ADR 2026-08-06：会话执行与观测通道解耦

## 状态

已采纳（2026-08-06）

## 背景

原先 `POST /api/chat` 的 SSE 生成器同时承载 Agent 执行与事件推送。客户端断开（关页、刷新、断网）会取消生成器，进而 `CancelledError` → 回合 `interrupted` + 沙箱 `interrupt_all`。长任务（如沙箱 job）无法在用户短暂离线后继续。

## 决策

1. **执行**挂在 `TurnExecutionHub` 的进程内 `asyncio.Task`（单 worker uvicorn 前提已成立）。
2. **观测**为可多路 `subscribe` 的 SSE；断开只退订 Queue，不 cancel Task。
3. **停止**仅经 `POST /api/chat/stop`（cancel Task + interrupt 沙箱）。进程启动时对 DB `running` 且无内存 Task 的孤儿只做 `finalize(interrupted)`。
4. 刷新后经 `GET /api/conversations/{cid}/turns/active/stream` 重连观测；入口 `getConversation.active_turn` 提示 running。
5. 无 `conversation_id` 的 ephemeral `/chat` 仍跟连接走（无落库锚点）。

## 后果

- 后端重启无法续跑内存中的 Task；启动时将 DB `running` 孤儿标为 `interrupted`。
- 不引入跨进程事件总线；多 worker 不在本决策范围。
