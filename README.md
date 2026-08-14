# Lore Chat

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/cnwinds/lore-chat/actions/workflows/ci.yml/badge.svg)](https://github.com/cnwinds/lore-chat/actions/workflows/ci.yml)

> **随口说，它帮你归位；随时问，它带你找回。**

对话式知识库：聊天即可记录与检索，内容保存为本地 Markdown。

## 快速开始

需要 [Docker](https://docs.docker.com/get-docker/) / Docker Desktop。

**Linux / macOS**

```bash
curl -fsSL https://raw.githubusercontent.com/cnwinds/lore-chat/master/deploy/get-lorechat.sh | bash
```

**Windows PowerShell**

```powershell
irm https://raw.githubusercontent.com/cnwinds/lore-chat/master/deploy/get-lorechat.ps1 | iex
```

打开 http://localhost:8080 。未配置 API Key 时，页面会引导填写。

## 本地开发

贡献流程、本机 venv / Vite 等见 [CONTRIBUTING.md](CONTRIBUTING.md)。

### Docker 开发模式（源码映射 + 热重载）

适合在容器里改代码、不希望每次改完都重建/重启镜像。叠加 `docker/docker-compose.dev.yml`：后端 bind-mount + `uvicorn --reload`，前端 Vite HMR。

1. 准备环境文件（若尚无）：

```bash
cp .env.docker.example .env
# 按需填写 OPENAI_API_KEY 等；也可启动后在网页「设置」填写
```

2. 启动：

```bash
./lorechat.sh start --chat --dev   # 仅核心栈
./lorechat.sh start --work --dev   # 核心 + OpenSandbox 沙箱
```

打开 http://localhost:${WEB_PORT:-8080}（默认 **8080**）。

| 服务 | 行为 |
|------|------|
| backend | 挂载 `backend/app` → 容器 `/app/app`，`uvicorn --reload` |
| web | 挂载 `frontend`，Vite 开发服务器（宿主机端口映射到容器 5173） |
| opensandbox | 仅 `--work` 时启用 |

常用命令：

```bash
./lorechat.sh log      # 跟日志
./lorechat.sh stop     # 停止
./lorechat.sh restart  # 按上次的 chat/work 与是否 --dev 重启
```

说明：

- 改 `backend/app` 或 `frontend` 源码一般**不必**重启容器。
- 改 `requirements.txt` / `package.json` 后需重建或进容器重装依赖（例如再次 `./lorechat.sh start … --dev`，或 web 容器内 `npm install`）。
- 运行时知识库默认在 `docker/data/knowledge`（可与仓库根 `data/knowledge` 做符号链接对齐已有数据）。
- 沙箱能力说明见 [ADR：OpenSandbox](docs/adr/2026-08-06-opensandbox-runtime.md)。

生产式本地构建（无热重载）：`./lorechat.sh start --chat` 或 `--work`。

## 更多

| | |
|--|--|
| 环境变量 | [`backend/.env.example`](backend/.env.example) |
| 模块地图 | [CONTEXT.md](CONTEXT.md) |
| 架构决策 | [docs/adr/](docs/adr/) |
| 安全披露 | [SECURITY.md](SECURITY.md) |
| 许可证 | [MIT](LICENSE) |
