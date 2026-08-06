# Spike NOTES

- time: 2026-08-06（本机跑通）
- domain: `127.0.0.1:18090`
- image: `python:3.12-slim`
- volume: `lorechat-opensandbox-workspace`
- result: **PASS**
- SDK: `opensandbox==0.1.15`

## 验收结果

| 项 | 结果 |
|----|------|
| Compose 旁挂 server（持 sock） | PASS |
| 客户端无 sock，仅 HTTP/SDK | PASS |
| 短同步命令 | PASS（`echo` → stdout） |
| 前台流式关键节点 | PASS（`ExecutionHandlers.on_stdout` 收到 5 个 tick） |
| 后台 job + status/logs 轮询 | PASS（`RunCommandOpts(background=True)` → `get_command_status` / `get_background_command_logs`） |
| named volume 跨 destroy/create 持久 | PASS（`/workspace/marker.txt`） |

## 运维踩坑（必读）

1. **端口**：本机 `8090` 已被 `lorechat-web` 占用 → Spike 映射 `18090:8090`。
2. **`host_ip`**：客户端在**宿主机**时必须设 `127.0.0.1`。若用 `host.docker.internal`，宿主机侧健康检查会报 `Network connectivity error`（endpoint 不可达）。
3. **镜像预拉**：首次需 `opensandbox/server`、`opensandbox/execd:v1.0.18`、`opensandbox/egress:v1.1.0`、业务镜像（如 `python:3.12-slim`）。缺 `execd` 时创建失败。
4. **`execd:v1.0.18` 警告**：server 提示升级到 `v1.1.0+` 才有 `bwrap` / session-gate；命令执行仍可用，隔离能力偏弱。正式接入应升 execd。
5. **API 鉴权**：Spike 用 `OPENSANDBOX_INSECURE_SERVER=YES`；生产必须配 `server.api_key`，且仅本机/内网可达。
6. **PVC**：`docker volume create` 须先于 `Sandbox.create`；`Volume(pvc=PVC(claim_name=...), mount_path="/workspace")`。

## 下一步产品化（非本 Spike）

1. 正式编排：默认 `docker/docker-compose.yml`；带执行能力叠加 `docker/docker-compose.sandbox.yml`
2. lore-chat 内 `Runtime` 端口：`run` / `start_job` / `poll_job` / `workspace_*` / `publish_to_kb`（仅 `sandbox_enabled` 时注册工具）
3. 升级 execd、固定 API key、资源限额
4. 极简镜像 → 固化视频依赖 Dockerfile

## 复跑

```bash
cd docs/spikes/2026-08-06-opensandbox
docker compose up -d
OPENSANDBOX_DOMAIN=127.0.0.1:18090 python3 run_spike.py
```
