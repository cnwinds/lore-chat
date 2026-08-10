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

见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 更多

| | |
|--|--|
| 环境变量 | [`backend/.env.example`](backend/.env.example) |
| 模块地图 | [CONTEXT.md](CONTEXT.md) |
| 架构决策 | [docs/adr/](docs/adr/) |
| 安全披露 | [SECURITY.md](SECURITY.md) |
| 许可证 | [MIT](LICENSE) |
