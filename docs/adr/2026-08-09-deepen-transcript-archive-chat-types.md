# ADR 2026-08-09：Transcript / 归档 / 聊天类型 / 设置页拆分

## 状态

已采纳（2026-08-09）

## 背景

三轮 deepen 后仍余：ConversationStore 持有只读文本投影；`session_extractor` 混装时间线压缩；归档编排挤在 Organizer；`api.ts` 领域类型与 HTTP 纠缠；SettingsPanel 模型/Agent/KB 页签仍内联。

## 决策

1. **`ConversationTranscript`**：`iter_segments` / `full` / `indexable_text` / `llm_history` / `context_excerpt`；`ConversationStore` 保留同名兼容委托。
2. **`dialogue_timeline_pack`**：拥有 `compress_dialogue_timeline` 与预算打包；session 抽取器只产出 `SlotAction`。
3. **`ConversationArchiveWorkflow`**：归档合成 + `apply_placement(replace)`；`Organizer.summarize_conversation` 薄委托（对齐 `MergeWorkflow`）。
4. **前端**：`types/chat.ts` + `utils/chatMessageFormat.ts`（及 `kbPath`）；`api.ts` 以 fetch + re-export 为主；`timelineStream` 从领域类型导入。
5. **`ModelSettingsTab` / `AgentSettingsTab` / `KbBackupSettingsTab`**：设置页继续按页签加深。

## 后果

- 归档与文本投影可独立单测；记忆压缩与抽取职责分离。
- 前端 chat 类型变更不必打开千行 HTTP 模块。
