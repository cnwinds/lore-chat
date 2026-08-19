<p align="center">
  <img src="docs/brand/lore-wordmark-gh.svg" alt="Lore" width="240" />
</p>

# Lore Chat

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/cnwinds/lore-chat/actions/workflows/ci.yml/badge.svg)](https://github.com/cnwinds/lore-chat/actions/workflows/ci.yml)

> **让每次对话，长成你的知识与能力。**

**Lore Chat 是一个会随对话积累知识、记忆与能力的本地优先 AI 工作系统。**

传统 AI 的每次对话都像重新开始；Lore 会把有价值的交流沉淀为可找回的知识、可延续的记忆和可复用的能力。知识以本地 Markdown 保存，图片等媒体也归入同一知识空间。

## 不只是聊天，而是在共同成长

Lore 希望让你专注于提问、思考和判断，把记录、整理、召回与重复执行交给 AI。

**对话 → 知识 → 记忆 → Skill → 下一次更好的协作**

一次回答不再是终点。今天聊过的内容，可以成为明天继续思考的上下文；今天跑通的流程，可以成为以后随时调用的能力。

## 核心能力

### 1. 聊天，而不是先写知识

不必先想标题、目录和格式，像平时一样聊天即可。有价值的对话可以整理成结构化 Markdown，连同来源和上下文一起留在自己的知识空间里。

### 2. 沉淀学习，而不是反复搜索

需要时，Lore 可以结合本地知识与网络信息回答，并保留可追溯的来源。提问、追问和结论会继续留在会话中，让一次检索逐渐变成完整的学习轨迹。

### 3. 维护知识，而不是维护目录

新内容进入知识库时，AI 会结合现有内容判断应该新建、合并还是归入已有目录。目录始终由你掌控；你调整后的结构，也会成为后续整理时的上下文。

### 4. 沉淀 Skill，而不是重复劳动

周报、数据分析、内容制作等重复工作，可以被整理成 Skill。启用后，只需说明目标，Lore 就能按沉淀下来的方法调用工具、读取资料并执行完整流程。

### 5. 越用越懂你，而不是每次重新认识

Lore 会从长期对话中提炼与你有关、跨会话仍然成立的身份、偏好、目标、协作方式和约束。每条记忆都有边界，也可以查看、纠正或删除——理解由相处积累，控制权始终属于你。

### 6. AI 负责理解，脚本负责执行

需要理解语义和做判断的部分交给模型，需要稳定执行的部分交给工具、脚本和可选沙箱。这样既保留 AI 的灵活性，也让复杂流程更可控、更容易复用。

### 7. 选择合适的模型，而不是被模型绑定

Lore 支持配置不同的聊天、视觉与生图模型，并可在候选模型之间自动切换。你可以上传截图让具备视觉能力的模型理解图片，也可以让已配置的生图服务生成图片；模型生成的 SVG 会作为受限的矢量图片资产保存，并直接在信息流中安全预览。

> [!NOTE]
> 图片识别取决于所选聊天模型是否支持视觉输入；图片生成需要另行配置生图服务。不同模型和服务支持的能力可能不同。

### 8. 知识在自己的硬盘上，而不是锁在别人的云端

Lore 把沉淀下来的知识以 **Markdown 纯文本**写在本机目录里，图片等媒体也落在同一知识空间。开放格式意味着你可以随时用编辑器、Obsidian、Git 备份或其它工具打开——不依赖某家 SaaS，也不会因为换工具就丢数据。知识的所有权与长期可读性，始终在你这边。

## 为什么叫 Lore

[`lore`](https://www.etymonline.com/word/lore) 源自古英语 `lār`，有“学习、教导、知识”之意；在现代英语中，它也指围绕某个主题长期积累并传承的知识与故事。

`Lore` 不是一串功能的缩写。它隐喻的是人与 AI 在长期协作中共同积累的上下文、方法和理解：零散的对话不再随窗口关闭而消失，而是逐渐长成只属于你的知识与能力体系。

## 在线演示

完整演示站（访客只读）：[https://lore-chat.x.ddnsto.com/](https://lore-chat.x.ddnsto.com/)

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

默认拉取 **`latest`**。要锁定发行版，在安装目录 `.env` 中设置后执行 `./lorechat.sh update`：

```bash
LORECHAT_IMAGE_TAG=0.1.0
```

也可直接拉取对应标签的镜像，例如 `ghcr.io/cnwinds/lore-chat-backend:0.1.0`（还有 `lore-chat-web`、`lore-chat-sandbox-agent`）。Git 标签是 `v0.1.0`，**镜像标签不带 `v`**。版本说明见 [CHANGELOG.md](CHANGELOG.md) 与 [GitHub Releases](https://github.com/cnwinds/lore-chat/releases)。

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
| 版本与变更 | [`VERSION`](VERSION) · [CHANGELOG.md](CHANGELOG.md) |
| 模块地图 | [CONTEXT.md](CONTEXT.md) |
| 架构决策 | [docs/adr/](docs/adr/) |
| 文档地图 | [docs/README.md](docs/README.md) |
| 安全披露 | [SECURITY.md](SECURITY.md) |
| 许可证 | [MIT](LICENSE) |
