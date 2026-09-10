# 多角色沙箱池（方案 C）— 设计摘要

配套 [ADR 2026-09-10](adr/2026-09-10-role-scoped-sandbox.md)。

## 拓扑

```
lorechat-backend ──HTTP──► opensandbox-server ×1
                              │
                              ├─ agent + PVC  role=default
                              ├─ agent + PVC  role=analyst
                              └─ …            （按已绑定角色）
```

- 控制面一份；backend 不持 `docker.sock`
- 每个角色固定 `sandbox_id` + `volume_name`，写入 `.kb/sandbox_runtime.json` v2
- 模型工具不传 `sandbox_id`

## P0 / P1

| | P0（已做） | P1 |
|--|-----------|-----|
| 绑定 | 持久 role→sandbox+volume | 空闲 TTL 可 destroy 容器、留 PVC |
| 池 | `RoleSandboxPool.get` + per-role lock | `sandbox_max_roles` 拒绝/驱逐 |
| 中断 | 按会话/角色，禁止跨角色 interrupt_all | 同左 |

## 默认工作目录

| 场景 | cwd |
|------|-----|
| 交互回合 | `/workspace/conversations/{conversation_id}` |
| 定时任务 | `/workspace/schedules/{schedule_id}` |
| 显式指定 | 任意 `/workspace/...` |
