# ADR 2026-08-09：记忆调度 / 时间线 reducer / JobRunner / 遗留清理

## 状态

已采纳（2026-08-09）

## 背景

两轮 deepen 后仍余：ConversationStore 承载记忆调度 SQL；`updateTimeline` 困在 `api.ts`；沙箱 job 轮询在 tool_impl；按条记忆文件幽灵；Organizer._apply 绕过 writer 意图。

## 决策

1. **`MemoryExtractSchedule`**：dirty / CAS / idle / enqueue / immediate；`SessionMemoryObserve` 经 `conversations.memory_schedule`；store 保留兼容委托。
2. **`timelineStream`**：拥有 `updateTimeline` reduce；`api.ts` 仅 re-export；`TOOL_LABELS` → `toolLabels.ts`。
3. **`SandboxJobRunner`**：长任务 wait/poll/progress；`SandboxTools` 薄委托。
4. **删除** `MemoryObserver` / 按条 `llm_extractor` / `extractor` / `MemoryIntake`；门禁测试钉在 session 抽取。
5. **`KnowledgeWriter.apply_placement`**：Organizer._apply 委托；merge 注入 `reorganize_existing`。
6. **`useSkillTrayAttach` + `AccountSettingsTab`**：继续拆设置/托盘编排。

## 后果

- 记忆调度可独立测试；前端观测契约与 HTTP client 分离。
- 按条抽取路径不再出现在生产树中。
