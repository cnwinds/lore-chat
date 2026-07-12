# Lore Chat

> **随口说，它帮你归位；随时问，它带你找回。**

对话式知识库：你说内容，系统自动组织并保存为 Markdown；提问时混合检索并带来源回答。数据落在 `knowledge/` 目录，可直接浏览、编辑，并由 git 记录历史。

**本项目面向 Windows 开发环境**，控制脚本使用 PowerShell + `.bat`，无需 bash / WSL / Git Bash。

## 快速开始（推荐）

在 **PowerShell** 或 **CMD** 中，于项目根目录执行：

```powershell
.\lorechat.bat setup    # 首次：自动检测并安装 Python、Node.js、依赖
.\lorechat.bat dev      # 开发模式（热更新，改代码自动生效）
```

- 前端：http://localhost:5173
- 后端：http://localhost:8000
- 在 `backend\.env` 中填入 `OPENAI_API_KEY`

## 控制命令

| 命令 | 说明 |
|------|------|
| `setup` | 检测并自动安装运行环境 |
| `dev` | 开发模式（uvicorn --reload + Vite HMR） |
| `start` | 生产模式（Docker Compose） |
| `stop` | 停止服务 |
| `restart` | 重启服务 |
| `log` | 查看日志 |

```powershell
.\lorechat.bat dev
.\lorechat.bat stop
.\lorechat.bat log
```

## 手动启动（可选）

若不用控制脚本，可在 PowerShell 中分别启动：

**后端：**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env    # 编辑填入 API Key
.\.venv\Scripts\uvicorn.exe app.main:app --reload --host 0.0.0.0 --port 8000
```

**前端：**

```powershell
cd frontend
npm install
npm run dev
```

## Docker 生产部署

需安装 [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)。

```powershell
Copy-Item .env.docker.example .env    # 编辑填入 OPENAI_API_KEY
.\lorechat.bat start
```

默认访问 **http://localhost:8080**（可在 `.env` 中修改 `WEB_PORT`）。

架构：`web`（Nginx 静态前端 + 反向代理 `/api`）→ `backend`（FastAPI）。知识库数据持久化在 Docker 卷 `lorechat-knowledge`。

```powershell
docker compose up -d --build
docker compose logs -f
docker compose down
```

## 数据目录说明

知识库根目录由环境变量 `KB_PATH` 指定（默认 `./knowledge`）：

```
knowledge/                 ← git 仓库，可直接打开浏览/编辑
├── 技术/
│   └── docker/
│       └── 常用命令.md
├── attachments/           ← 附件原件
└── .kb/
    ├── index/             ← 向量/全文索引（可删除后重建）
    ├── pending.json       ← 待用户确认的归置问题
    └── changelog.md       ← AI 整理操作记录
```

- **Markdown 文件**是唯一事实来源；索引仅为加速缓存。
- **git 历史**记录每次写入与整理，可随时回滚。
- **`.kb/changelog.md`** 汇总 AI 的归置与变更说明，便于审计。

## Agent 对话

Lore Chat 使用**统一 Agent**：直接聊天即可，无需说「记录」或切换模式。Agent 会按需检索本地知识库、搜索网页、抓取链接，并在后台静默整理落库。

| 能力 | 说明 |
|------|------|
| 本地检索 | 自动 `search_kb` / `read_doc` |
| 联网搜索 | 配置任一搜索 API 后可用（见下） |
| 静默落库 | 有价值内容自动 `write_kb`，可在侧边栏查看 |
| 时间线 | 工具步骤、来源、耗时以 SSE 流式推送并持久化到会话 |

**显式口令（可选）：**「帮我记录」「别保存」「只搜不写」「搜一下」等可覆盖默认行为。

### 网页搜索 API

在 `backend\.env` 中配置**至少一个**密钥即可；系统按 `SEARCH_PROVIDER_ORDER` 顺序尝试：

| 变量 | 提供商 |
|------|--------|
| `TAVILY_API_KEY` | [Tavily](https://tavily.com/) |
| `SERPER_API_KEY` | [Serper](https://serper.dev/) |
| `BRAVE_SEARCH_API_KEY` | [Brave Search API](https://brave.com/search/api/) |

未配置任何搜索密钥时，Agent 仍可使用本地知识库与 URL 抓取，但无法联网搜索。

### Agent 配置

在 `backend\.env`（参考 `backend\.env.example`）中可调：

| 变量 | 默认 | 说明 |
|------|------|------|
| `AGENT_MAX_TOOL_CALLS` | `8` | 单轮最多工具调用次数 |
| `AGENT_PARALLEL_TOOLS` | `true` | 只读工具是否并行 |
| `AGENT_MAX_PARALLEL` | `4` | 单批最多并行数 |
| `FETCH_URL_TIMEOUT` | `15` | URL 抓取超时（秒） |
| `FETCH_URL_MAX_BYTES` | `102400` | URL 抓取最大字节 |
| `SEARCH_PROVIDER_ORDER` | `tavily,serper,brave` | 搜索提供商优先级 |
