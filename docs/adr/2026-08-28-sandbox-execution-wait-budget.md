# ADR: 沙箱执行 wait 预算与检查点

- **日期**: 2026-08-28
- **状态**: 已采纳

## 背景

Agent 在沙箱中执行长命令（如 `douyin2text.py`、Docker 构建）时，原先存在两种路径：

1. 前台 `run(timeout)` — 理论上可流式，但 OpenSandbox sync API 在长超时场景下体验不稳定；
2. `background=true` + job 轮询 — 输出常整段到达，且 Agent 无法在软限时内审查进度。

用户要求：**任意模式均流式输出**；软限时由 **Agent 决策**（不弹 UI）；约 **每 60 秒检查点** 交还控制权，Agent 可续等、优化或停止。

## 决策

引入 `SandboxExecutionEngine`，统一所有 `sandbox_run` 为 **后台 job + poll 流式**：

| 参数 | 默认 | 含义 |
|------|------|------|
| `wait_sec` | 60 | 本段等待预算（秒） |
| `if_exceeded` | `return` | 预算用尽时的行为 |
| `execution_id` | — | 续接已有任务 |

`if_exceeded` 取值：

- `return` — 检查点：返回 `running=true, checkpoint=true, wait_exceeded=true`，Agent 审查后 `execution_id` 续接、`wait_until_done` 或 `sandbox_stop`
- `wait_until_done` — 忽略预算，poll 直到完成
- `stop` — 预算到期则 `interrupt` 并返回

新增 `sandbox_stop(execution_id)` 强制停止。

废弃 `background`、`timeout_sec` 工具参数（内部 `run(timeout)` 仍用于 mkdir 等 bootstrap，不对 Agent 暴露）。

`ExecutionRegistry` 进程内维护 cursor 与累积日志，支持跨 `sandbox_run` 续接。

命令经 `prepare_streaming_command` 自动加 `PYTHONUNBUFFERED=1`（Python 类命令）。

## 后果

- Agent SYSTEM_PROMPT / tool_catalog 须描述 60s 检查点工作流
- 单测覆盖 checkpoint、attach、stop、wait_until_done
- 与 stale sandbox 自动重建正交：热路径不探活，由 `_call_sandbox` 在可恢复错误时清缓存并重建后重试一次

## 参考

- `backend/app/engine/sandbox/execution_engine.py`
- `backend/app/engine/sandbox/execution_registry.py`
- `backend/app/engine/agent/tool_impl/sandbox_tools.py`
