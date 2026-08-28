# 架构决策记录（ADR）

记录**已采纳**的结构取舍。新决策单独成篇，不改写旧文；现状以代码与 [CONTEXT.md](../../CONTEXT.md) 为准。

| 日期 | 决策 |
|------|------|
| [2026-08-04](2026-08-04-engine-module-seams.md) | 引擎模块 seam（KnowledgeWriter / 聊天观测 / 归位） |
| [2026-08-05](2026-08-05-merge-ui-only.md) | 多文档合并只走 UI MergeWorkflow |
| [2026-08-06](2026-08-06-opensandbox-runtime.md) | Agent 执行采用 OpenSandbox |
| [2026-08-06](2026-08-06-turn-execution-observe.md) | 回合执行与 SSE 观测解耦 |
| [2026-08-08](2026-08-08-deepen-memory-turn-tools.md) | 加深记忆 / 回合 / 工具 / 时间线 |
| [2026-08-08](2026-08-08-deepen-sandbox-settings-outbound.md) | 加深沙箱确认 / KB 交换 / 设置 / 出站队列 |
| [2026-08-09](2026-08-09-deepen-schedule-timeline-job.md) | 记忆调度 / 时间线 reducer / JobRunner |
| [2026-08-09](2026-08-09-deepen-viewport-bridge-memory-store.md) | KB viewport / 托盘桥 / 记忆写策略 |
| [2026-08-09](2026-08-09-deepen-deletion-transport-stream.md) | 删除 / 消息图 / HTTP 传输 / 流投影 |
| [2026-08-09](2026-08-09-deepen-transcript-archive-chat-types.md) | Transcript / 归档 / 聊天类型 / 设置拆分 |
| [2026-08-12](2026-08-12-image-generation-providers.md) | 多厂商生图 ImageGen |
| [2026-08-28](2026-08-28-sandbox-execution-wait-budget.md) | 沙箱 wait 预算与 60s 检查点 |
