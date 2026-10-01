# ADR 2026-09-30：后台流程视图与调用登记

## 状态

已采纳（2026-09-30）。

## 背景

主对话已有请求快照（[ADR 2026-09-30 request-snapshots](2026-09-30-request-snapshots.md)），但记忆抽取、卡片整理、归档成文等后台 LLM 调用对主人不可见，配置变更（空闲时长、衰减间隔）也存在热更新缺口。

## 决策

1. **purpose 标注**：每个后台 `llm.chat` / 派生 `embed_pending` 调用经 `llm_purpose(...)` 写入 `ContextVar`；用量事件增加 `purpose` 列。
2. **独立快照库**：`background_calls.db` 按 purpose 保留最近 30 条，脱敏与截断策略对齐主对话快照；失败不影响调用。
3. **只读 catalog**：HTTP `GET /api/admin/background*` 组合静态 catalog（import 真实提示词）+ 运行状态 + 积压 + 统计；提示词不在 UI 编辑。
4. **暂停开关**：`background_paused` 三项语义固定（跳过抽取 / 整理 / 进化），改配置仍走 `PUT /api/admin/settings`。
5. **配置热更新**：`apply_settings` 同步 `memory_worker.idle_hours` 与 `MemoryMaintenanceJob` 衰减配置；memory-maintenance 线程间隔读 `memory_maintenance_interval_hours`。

## 后果

- 主人可在设置中打开后台流程图，查看提示词、最近调用与相关数字配置。
- 后台快照与会话/作用域同生命周期删除。
- catalog 与代码提示词须保持一致；抽取/整理类改动需对照 catalog 契约测试。
- 修订 request-snapshots ADR 中「后台调用不记」：后台改记 `background_calls.db`，主对话仍只记 `requests.db`。
