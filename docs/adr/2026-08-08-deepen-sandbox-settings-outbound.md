# ADR 2026-08-08：加深沙箱确认 / KB 交换 / 设置热应用 / 出站编排

## 状态

已采纳（2026-08-08）

## 背景

架构审查（记忆/回合加深之后）发现：沙箱确认泄漏进 Organizer；SandboxTools 叠交换与轮询；检索设置热应用不刷新 Retriever；前端发送队列半加深；非 MD 资产政策分裂。

## 决策

1. **`SandboxCommandGate`**：创建/解析 `sandbox_confirm`；Organizer 拒收该类 payload；`PendingResolver` 直接走 gate。
2. **`KbSandboxExchange`**：stage/publish、workspace 路径与批量 args 收进 deep module；读侧经 `KnowledgeWriter.read_entry_bytes`；publish 默认 `allow_binary=False`。
3. **`IndexSubgraph.apply_settings` + `AgentSubgraph.publish`**：`apply_settings` 只编排；检索 tunables 热生效。
4. **`useOutboundOrchestrator`**：flush/inject/pause 编排离开 `Chat.tsx`；策略仍在 `outboundQueue`。
5. **非 MD 准入**：`KnowledgeWriter.assert_non_md_asset_allowed`；HTTP import `allow_binary=True`。
6. **前端 `timelineStream.mergeServerTimeline`**；用量 `usage.normalize`。

## 后果

- 沙箱确认与 KB 摄入测试面分离。
- 设置页改检索参数后无需重启即可生效。
- Agent/publish 不能再落任意二进制；树上传仍可。
