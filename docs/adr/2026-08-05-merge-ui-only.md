# ADR 2026-08-05：多文档合并仅走 UI MergeWorkflow

## 状态

已采纳（2026-08-05）

## 背景

托盘多文合并在 HTTP 侧有完整审阅会话（`MergeWorkflow`：预览、接受、拒绝、清理源文档）。
Agent 工具层若再用 `write_doc` + `ask_user` 模拟合并，会出现两套语义与测试面。

## 决策

1. **多文档合并**（用户托盘勾选多篇后合并）**仅**经 UI / `POST /api/docs/merge*` → `MergeWorkflow`。
2. Agent **不**新增 `merge_documents` 工具；prompt 明确：托盘多篇合并引导用户用侧栏/合并 UI，勿用 `write_doc` 伪合并后擅自 `delete_kb`。
3. Agent 仍可用 `write_doc` / `edit_doc` 做单篇写入或局部改；`write_mode=replace|merge|auto`（已存在文档默认 merge）。

## 后果

- 合并审阅与源清理只维护一条路径
- Agent 侧降低误删风险；若未来要 Agent 合并，须直接委托 `MergeWorkflow` 并复用审阅会话，再修订本 ADR
