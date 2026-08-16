# ADR 2026-08-08：加深记忆 / 回合 / 工具 / 时间线 seam

## 状态

已采纳（2026-08-08）

## 背景

2026-08-04 / 08-06 ADR 已拆出 KnowledgeWriter、TurnExecutionHub、OpenSandbox。架构审查仍发现：会话定稿观察编排泄漏、记忆写路径分叉、ToolRegistry 透传、ChatSessionRunner 过浅、前后端双时间线 reducer、KbEntryOps 透传、按条 observe 遗留占 locality。

## 决策

1. **`SessionMemoryObserve`**：dirty / idle / extract / resolve / CAS 收进 deep module；`MemoryWorker` 为兼容别名；backfill 经 `batch_mark_dirty_and_enqueue_session_observe`，不摸私有 lock。
2. **写事实唯一 `SlotResolver`**：confirm / edit / correct / forget / reject 经 `MemoryService.resolver`；面板与自动抽取同测面。
3. **`ToolRegistry`**：dispatch 直挂 `tool_impl`；对外 `execute` / `rebind` / `interrupt_runtime`；hub stop 不穿 `.sandbox.runtime`。
4. **回合生命周期在 Hub**：`begin_and_ensure` + `subscribe`；HTTP 经 `ChatSessionRunner.begin_persisted_turn` / `observe_turn`。
5. **`timeline_state` SSE（投影 + 增量分工）**：
   - 持久回合由后端 `TimelineAccumulator` 维护权威时间线。
   - **结构事件**（`tool_start` / `tool_result` / `parallel_batch_*` / `user_inject`）经 `timeline_state` 全量投影下发；前端 `serverTimeline` 后对这些事件**跳过** client reduce，只 apply 投影。
   - **流式增量**（`text_delta` / `think_delta` / `tool_progress`）只发原始 SSE，**不**随每个 token 再推全量投影（避免观测 buffer O(n²) / OOM）。前端在已切 `serverTimeline` 后仍对这类增量本地 `updateTimeline`。
   - ephemeral 无投影时，全部事件仍本地 `updateTimeline`。
6. **删除浅 `KbEntryOps`**：Agent/Merge 走 `Organizer.ingest_text` / `KnowledgeWriter.delete_entry|move_entry`。
7. **按条 observe 废除**：`MemoryIntake` 构造即失败；政策测试钉在 `SlotResolver`。

## 后果

- 记忆与回合测试可打更小的生产 interface。
- 观测 SSE 多一类 `timeline_state` 事件；旧客户端仍可读原始 tool/text 事件（兼容）；新 UI：结构靠投影，token/进度靠增量。
- Hub 观测 buffer 对 `timeline_state` 只保留最新一条，并在 retain 窗口到期后淘汰已结束 turn。
- `kb_entry_ops.py` 仅 re-export `WriteMode`。
