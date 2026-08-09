# Lore Chat

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/cnwinds/lore-chat/actions/workflows/ci.yml/badge.svg)](https://github.com/cnwinds/lore-chat/actions/workflows/ci.yml)

> **随口说，它帮你归位；随时问，它带你找回。**

对话式知识库：你说内容，系统自动组织并保存为 Markdown；提问时混合检索并带来源回答。数据落在 `knowledge/` 目录，可直接浏览、编辑，并由 git 记录历史。

支持 **Linux / macOS / Windows**。推荐用 Docker 部署；本地开发可用 `lorechat.sh`（Unix）或 `lorechat.bat`（Windows）。

## 功能要点

| 能力 | 说明 |
|------|------|
| 统一 Agent | 直接聊天即可，无需切换「记录 / 问答」模式 |
| 本地检索 | 自动 `search_kb` / `read_doc` |
| 联网搜索 | 配置任一搜索 API 后可用（见下） |
| 静默落库 | 有价值内容自动写入知识库，可在侧边栏查看 |
| 时间线 | 工具步骤、来源、耗时以 SSE 流式推送并持久化 |

**显式口令（可选）：**「帮我记录」「别保存」「只搜不写」「搜一下」等可覆盖默认行为。

## 快速开始（推荐：Docker）

适用于 Linux、macOS、Windows（需 [Docker](https://docs.docker.com/get-docker/) / Docker Desktop）。

```bash
# 1. 配置环境变量
cp .env.docker.example .env
# 编辑 .env，填入 OPENAI_API_KEY

# 2. 启动
./lorechat.sh start          # Linux / macOS
# 或
docker compose --project-directory docker --env-file .env -f docker/docker-compose.yml up -d --build
```

Windows PowerShell：

```powershell
Copy-Item .env.docker.example .env
# 编辑 .env，填入 OPENAI_API_KEY
docker compose --project-directory docker --env-file .env -f docker/docker-compose.yml up -d --build
```

默认访问 **http://localhost:8080**（可在 `.env` 中修改 `WEB_PORT`）。

架构：`web`（Nginx 静态前端 + 反向代理 `/api`）→ `backend`（FastAPI）。运行数据在 `docker/data/`（知识库、备份）——**本地私有，请勿提交到 git**。

### 可选：OpenSandbox 执行能力

```bash
docker compose --project-directory docker --env-file .env \
  -f docker/docker-compose.yml -f docker/docker-compose.sandbox.yml up -d --build
```

`GET /api/health` 的 `capabilities.sandbox` 为 `true` 时表示已启用执行 Runtime。详见 [ADR：OpenSandbox Runtime](docs/adr/2026-08-06-opensandbox-runtime.md)。

构建已配置国内 apt / PyPI / npm 源。若拉取基础镜像仍慢，可将 [docker/daemon.json.example](docker/daemon.json.example) 中的 `registry-mirrors` 合并进 Docker 引擎配置后重启。

## 本地开发

前置：Python **3.12+**、Node.js **20+**。

### Linux / macOS

```bash
cp backend/.env.example backend/.env   # 填入 OPENAI_API_KEY
./lorechat.sh setup
./lorechat.sh dev
```

### Windows

```powershell
Copy-Item backend\.env.example backend\.env
.\lorechat.bat setup
.\lorechat.bat dev
```

- 前端：http://localhost:5173
- 后端：http://localhost:8000

### 控制命令

| 命令 | Linux/macOS | Windows | 说明 |
|------|-------------|---------|------|
| `setup` | `./lorechat.sh setup` | `.\lorechat.bat setup` | 安装依赖 / 准备环境 |
| `dev` | `./lorechat.sh dev` | `.\lorechat.bat dev` | 开发模式（热更新） |
| `start` | `./lorechat.sh start` | 见上方 Docker | Unix 脚本走 Docker Compose；Windows bat 为本地生产 uvicorn |
| `stop` | `./lorechat.sh stop` | `.\lorechat.bat stop` | 停止服务 |
| `restart` | `./lorechat.sh restart` | `.\lorechat.bat restart` | 重启 |
| `log` | `./lorechat.sh log` | `.\lorechat.bat log` | 查看日志 |

### 手动启动（可选）

**后端：**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # 编辑填入 API Key
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**前端：**

```bash
cd frontend
cp .env.example .env               # 开发可保持 VITE_API_BASE 为空
npm install
npm run dev
```

## 环境变量

| 用途 | 文件 |
|------|------|
| Docker Compose | [`.env.docker.example`](.env.docker.example) → 根目录 `.env` |
| 本地后端 | [`backend/.env.example`](backend/.env.example) → `backend/.env` |
| 本地前端 | [`frontend/.env.example`](frontend/.env.example) → `frontend/.env` |

### 网页搜索 API（可选）

在 `backend/.env`（或 Docker 根 `.env` 若已透传）中配置**至少一个**密钥；按 `SEARCH_PROVIDER_ORDER` 顺序尝试：

| 变量 | 提供商 |
|------|--------|
| `TAVILY_API_KEY` | [Tavily](https://tavily.com/) |
| `SERPER_API_KEY` | [Serper](https://serper.dev/) |
| `BRAVE_SEARCH_API_KEY` | [Brave Search API](https://brave.com/search/api/) |

未配置时 Agent 仍可使用本地知识库与 URL 抓取，但无法联网搜索。

### Agent 调优（节选）

详见 `backend/.env.example`：

| 变量 | 默认 | 说明 |
|------|------|------|
| `AGENT_MAX_TOOL_CALLS` | `25` | 单轮最多工具调用次数 |
| `AGENT_PARALLEL_TOOLS` | `true` | 只读工具是否并行 |
| `AGENT_MAX_PARALLEL` | `4` | 单批最多并行数 |
| `FETCH_URL_TIMEOUT` | `15` | URL 抓取超时（秒）；实际 `max(该值, 60)` |
| `SEARCH_PROVIDER_ORDER` | `tavily,serper,brave` | 搜索提供商优先级 |

## 数据目录

**Docker：** `docker/data/knowledge/`（容器内 `KB_PATH=/data/knowledge`），备份在 `docker/data/backups/`。

**本地开发：** `KB_PATH` 指定知识库根（默认 `backend/knowledge`）。

```
docker/data/knowledge/     ← Docker 运行时知识库（可直接浏览/编辑）
├── …/
├── attachments/           ← 附件原件
└── .kb/
    ├── index/             ← 向量/全文索引（可删除后重建）
    ├── pending.json       ← 待用户确认的归置问题
    └── changelog.md       ← AI 整理操作记录
```

- **Markdown** 是唯一事实来源；索引仅为加速缓存。
- 运行时知识库与备份为**本地私有数据**，已被 `.gitignore` 排除，请勿提交。

## 贡献与安全

- 贡献指南：[CONTRIBUTING.md](CONTRIBUTING.md)
- 行为准则：[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- 安全披露：[SECURITY.md](SECURITY.md)
- 模块地图：[CONTEXT.md](CONTEXT.md)
- ADR：[docs/adr/](docs/adr/)

## 许可证

[MIT](LICENSE) © cnwinds
