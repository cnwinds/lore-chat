# ADR 2026-09-10：每角色固定绑定执行沙箱（方案 C）

## 状态

已采纳（2026-09-10）；**P0 与 P1 均已落地**

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
- 高风险确认 payload / 文案带上 `role_id` + `role_name` + `conversation_id`，批准后仍打同一 slot；待确认 UI 显示角色名与 id

### 4. 同角色 cwd 默认

同一角色共享一张盘，用子目录降低互踩：

- 交互回合：`/workspace/conversations/{conversation_id}`
- 定时任务：`/workspace/schedules/{schedule_id}`
- 显式 `cwd` 仍允许，但必须在 `/workspace` 下

### 5. P1：池上限、空闲回收、删角色、健康面

| 设置 | 默认 | 热改 | 行为 |
|------|------|------|------|
| `sandbox_max_roles` | **4** | 是 | 进程内活容器数上限。已占用 slot 的角色可继续 `get`。新角色在满员且无法回收空闲时，工具返回中文错误 `sandbox_pool_full`，**绝不借用**他人沙箱 |
| `sandbox_idle_ttl_sec` | **3600** | 是 | 无活跃 execution 且超过 TTL → `kill` 容器，**保留 PVC 与 slot**，清 `sandbox_id` 并标 `reclaimable`；下次 `get` 按原卷重连/重建。`0` = 不自动回收 |
| `sandbox_destroy_volume_on_role_delete` | **false** | 是 | 删角色时先 interrupt + 毁容器。默认留卷与 slot；为 true 时忘记 slot（OpenSandbox 对已存在的 named volume 不会随 kill 删除，控制面无独立删卷 API） |

- 空闲回收在 `get` 需要新活容器时、以及 `reclaim_idle()` 中执行
- `GET /api/health` capabilities 增加 `sandbox_pool: { max, active, busy_roles }`
- 设置 → Agent 可改上述三项（部署级 `sandbox_enabled` / 镜像 / 卷名仍只读）

### 6. 明确非目标

- 不复制 `opensandbox-server`
- 不把 docker.sock 挂进 backend
- 不把 `sandbox_id` 暴露为模型必填参数

## 后果

- 修订 ADR 2026-08-06「一个长驻沙箱」：控制面仍一个，**执行沙箱按角色一份**
- 运维面上每多一个活跃角色多一个 agent 容器 + 一张卷；默认卷名不变，旧部署可迁移
- 同角色多会话仍共享 `/workspace`（靠子目录约定）；跨角色并行不再互相 interrupt
- 超过 `sandbox_max_roles` 的新角色会失败，直到有空闲容器被 TTL 回收或主人提高上限

## 修订关系

本文**不改写** [2026-08-06](2026-08-06-opensandbox-runtime.md) 原文；该文「一个长驻沙箱」以本文与代码为准。
