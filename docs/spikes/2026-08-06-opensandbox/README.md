# OpenSandbox Spike（2026-08-06）

对应 ADR：`docs/adr/2026-08-06-opensandbox-runtime.md`

## 验收目标

1. Compose 旁挂 `opensandbox-server`（持有 `docker.sock`）；spike 客户端**不**挂 sock
2. 创建带 named volume 的沙箱，挂载到 `/workspace`
3. 短同步命令 + 流式 stdout 回调
4. 较长前台命令（多段 sleep/echo）验证关键节点式输出
5. 写入 `/workspace` 后销毁并重建沙箱，确认卷内文件仍在

## 目录

| 文件 | 说明 |
|------|------|
| `docker-compose.yml` | OpenSandbox server |
| `config.toml` | server 配置 |
| `run_spike.py` | Python SDK 验收脚本 |
| `NOTES.md` | 跑完后的结论（由脚本/人工填写） |

## 运行

```bash
cd docs/spikes/2026-08-06-opensandbox

# 0. 预拉依赖镜像（强烈建议）
docker pull opensandbox/server:latest
docker pull opensandbox/execd:v1.0.18
docker pull opensandbox/egress:v1.1.0
docker pull python:3.12-slim

# 1. 启动控制面（宿主机 18090 → 容器 8090；避开 lorechat-web:8090）
docker compose up -d

# 2. 客户端依赖（宿主机或 venv）
python3 -m pip install -U 'opensandbox'

# 3. 跑验收
OPENSANDBOX_DOMAIN=127.0.0.1:18090 python3 run_spike.py
```

配置要点：`config.toml` 里 `[docker] host_ip = "127.0.0.1"`（客户端在宿主机时）；见 `NOTES.md`。

清理：

```bash
docker compose down
# 可选：docker volume rm lorechat-opensandbox-workspace
```
