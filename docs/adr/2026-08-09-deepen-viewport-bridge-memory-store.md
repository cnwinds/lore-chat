# ADR 2026-08-09：加深 KB viewport / 托盘桥 / 记忆写策略 / Store 子域

## 状态

已采纳（2026-08-09）

## 背景

架构审查热点：KB 树展开与滚动跨文件握手；App 仍堆托盘↔预览状态机；记忆按条政策残骸与 status 分叉；ConversationStore 宽 facade 下摘要/系统事件未切出。

## 决策

1. **`useKbTreeViewportUi`**：展开 + 滚动 hydrate/restore/persist 收进一个 deep module；`FileTree` 受控渲染；删除 `onExpandReady` 握手与 `useKbTreeScrollUi`。
2. **`useComposerPreviewBridge`**：文档托盘 ↔ float/pin 预览编排离开 `App.tsx`（对称 `useSkillTrayAttach`）。
3. **记忆写策略**：`policy.py` 仅保留 SlotResolver 仍用的规则；`initial_status` 唯一实现；删除 `MemoryCandidate` / 证据门禁与孤儿测面。抽取器只透传 LLM `slot_hint`，槽位身份只在 `SlotResolver` 解析；时间线 pack 仅经公开 API。
4. **`ConversationSummaryLedger` / `ConversationSystemEvents`**：从 Store 切出；生产 caller 直打 `store.summaries` / `store.system_events`；Store 保留薄兼容委托，停止在此再堆实现。Ledger 经 `latest_message_id_unlocked` / `notify_archived_unlocked` 意图钩子调度，不直接写 messages SQL。
5. **`SlotAction.slot_hint`**：抽取器只填 hint；`slot_key` 属性为兼容别名；canonical 槽位只在 `SlotResolver.apply` 解析。

## 后果

- 侧栏树 UI 与托盘预览可独立测；记忆写路径 locality 回到 Resolver。
- Store 收口未完成（CRUD / message window 等仍在）；后续勿再加兼容委托实现体。
