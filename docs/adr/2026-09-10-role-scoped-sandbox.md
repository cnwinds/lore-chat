# ADR 2026-09-10：每角色固定绑定执行沙箱（方案 C）

## 状态

已采纳（2026-09-10）

## 背景

[ADR 2026-08-06](2026-08-06-opensandbox-runtime.md) 假定**单操作者、一个长驻沙箱**：`.kb/sandbox_runtime.json` 顶层一个 `sandbox_id`，Compose 预创建一张 PVC `lorechat-sandbox-workspace`，`interrupt_all` 打在这份共享 runtime 上。

多角色并行（[ADR 2026-09-09](2026-09-09-multi-role-shell.md)）之后，两个角色的 turn / 定时任务会：

- 抢写同一 `/workspace`
- 一方 stop / cancel 时 `interrupt_all` 打断另一方

知识库与主人记忆仍全局共享；需要隔离的是**执行盘与进程**，不是再开一套控制面。

## 决策

### 1. 拓扑（方案 C）

| 层 | 数量 | 说明 |
|----|------|------|
| `opensandbox-server` | **×1** | 唯一控制面；backend **不**挂 `docker.sock` |
| Agent 容器（execd / 业务镜像） | **×N** | 每个**已激活**角色一把 |
| PVC / named volume | **×N** | 每角色固定一张，挂 `/workspace` |

角色与 `sandbox_id` + `volume_name` **固定绑定**。进程重启后按 slot 重连；容器可重建，卷默认保留。

### 2. `RoleSandboxPool` + state v2

绑定落在 `.kb/sandbox_runtime.json` **version 2**：

```json
{
  "version": 2,
  "slots": {
    "<role_id>": {
      "sandbox_id": "...",
      "volume_name": "lorechat-sandbox-ws-<slug>",
      "mirror_region": "cn",
      "updated_at": "..."
    }
  },
  "migrated_from_v1": true
}
```

- v1 顶层 `sandbox_id` + 现有默认卷名迁到默认角色 slot，**不丢盘**
- 默认角色继续用 compose 预创建的 `lorechat-sandbox-workspace`
- 其他角色：`lorechat-sandbox-ws-<docker-safe-slug>`，由 OpenSandbox `PVC(create_if_not_exists)` 创建
- `get(role_id)` 带 per-role `asyncio.Lock` 包 `ensure_ready`
- `interrupt_role` / `interrupt_execution` **只打该角色**；禁止跨角色 `interrupt_all`

### 3. 工具 / stop / pending

- `SandboxTools` 从 `conversation.role_id`（或 pending 回放的 `role_id`）解析 slot，**永不借用**其他角色 runtime
- 不把 `sandbox_id` 暴露为模型必填工具参数
- 聊天 stop：只中断该会话所属角色的执行
- `ExecutionRegistry` 记录 `role_id` + `conversation_id`（可选 `schedule_id`）
- 高风险确认 payload 带上 `role_id` + `conversation_id`，批准后仍打同一 slot

### 4. 同角色 cwd 默认

同一角色共享一张盘，用子目录降低互踩：

- 交互回合：`/workspace/conversations/{conversation_id}`
- 定时任务：`/workspace/schedules/{schedule_id}`
- 显式 `cwd` 仍允许，但必须在 `/workspace` 下

### 5. 明确非目标（P0）

- 不复制 `opensandbox-server`
- 不把 docker.sock 挂进 backend
- **P1**：`sandbox_max_roles` 硬上限、空闲 TTL 销毁容器并保留 PVC（P0 只留设置挂钩与注释）

## 后果

- 修订 ADR 2026-08-06「一个长驻沙箱」：控制面仍一个，**执行沙箱按角色一份**
- 运维面上每多一个活跃角色多一个 agent 容器 + 一张卷；默认卷名不变，旧部署可迁移
- 同角色多会话仍共享 `/workspace`（靠子目录约定）；跨角色并行不再互相 interrupt

## 修订关系

本文**不改写** [2026-08-06](2026-08-06-opensandbox-runtime.md) 原文；该文「一个长驻沙箱」以本文与代码为准。
