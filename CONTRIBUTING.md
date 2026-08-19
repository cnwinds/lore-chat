# Contributing to Lore Chat

感谢你愿意改进 Lore Chat。提交代码前请先阅读本指南与行为准则 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 开始之前

1. 浏览模块地图与 seam 约定：[CONTEXT.md](CONTEXT.md)
2. 相关架构决策见 [`docs/adr/`](docs/adr/)
3. 提示词相关改动须遵守根目录 [AGENTS.md](AGENTS.md)（根因治理，禁止孤例补丁）
4. **发布版本**须遵守 [AGENTS.md「版本发布」](AGENTS.md#二版本发布)：改 `VERSION` + `CHANGELOG.md`，在 `master` 打 annotated tag `vX.Y.Z` 并推送；CI 发布 GHCR `latest` / `vX.Y.Z` 镜像并创建 GitHub Release

**请勿提交**：API 密钥、本机 `.env`、以及 `docker/data/` / `deploy/data/` / 启动器旁 `data/` / `backend/knowledge/` 下的运行时知识库与备份（这些目录为本地私有数据）。

## 开发环境

### 本地开发

前置：Python **3.12+**、Node.js **20+**。

**Linux / macOS**

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
./lorechat.sh setup
./lorechat.sh dev
```

**Windows**

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
.\lorechat.bat setup
.\lorechat.bat dev
```

- 前端：http://localhost:5173
- 后端：http://localhost:8000

源码 Docker：

- **开发热重载**（推荐改代码时用）：`cp .env.docker.example .env && ./lorechat.sh start --chat --dev`（或 `--work --dev`）。详见 [README「Docker 开发模式」](README.md#docker-开发模式源码映射--热重载)。
- **生产式本地构建**：`./lorechat.sh start --chat` / `--work`（沙箱见 [ADR](docs/adr/2026-08-06-opensandbox-runtime.md)）。

## 测试

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest

# Frontend
cd frontend
npm ci
npm run lint
npm test
npm run build
```

CI：PR 跑 [ci.yml](.github/workflows/ci.yml)；推送到 `master`/`main` 或 `v*` tag 时由 [publish-images.yml](.github/workflows/publish-images.yml) 先跑同一套检查再推镜像。`master` 更新 `latest`；`vX.Y.Z` tag 额外打出 `vX.Y.Z`、`vX.Y`（及不带 `v` 的别名）并写 GitHub Release。检查步骤见 [ci-checks.yml](.github/workflows/ci-checks.yml)。发布操作步骤见 [AGENTS.md](AGENTS.md#二版本发布)。

## Pull Request

1. 从最新 `master` 开分支，保持变更聚焦、可审查
2. 若改动用户可见行为或 API，请在 PR 描述中说明动机与验证方式
3. 涉及提示词：在描述中写明根因类别与验收意图（对照 AGENTS.md 清单）
4. 确保本地测试通过；勿在 PR 中附带个人知识库文件或密钥
5. 使用仓库提供的 PR 模板填写摘要与测试计划

Issue / 功能建议请使用 GitHub Issue 模板。安全问题请走 [SECURITY.md](SECURITY.md)，不要公开开 Issue。

## 许可证

贡献一经合并，即视为同意以项目 [MIT License](LICENSE) 授权。
