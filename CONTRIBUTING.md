# Contributing to Lore Chat

感谢你愿意改进 Lore Chat。提交代码前请先阅读本指南与行为准则 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 开始之前

1. 浏览模块地图与 seam 约定：[CONTEXT.md](CONTEXT.md)
2. 相关架构决策见 [`docs/adr/`](docs/adr/)
3. 提示词相关改动须遵守根目录 [AGENTS.md](AGENTS.md)（根因治理，禁止孤例补丁）

**请勿提交**：API 密钥、本机 `.env`、以及 `docker/data/` / `backend/knowledge/` 下的运行时知识库与备份（这些目录为本地私有数据）。

## 开发环境

### 推荐：Docker（任意平台）

见 [README.md](README.md) 的 Docker 章节。适合验证部署与联调，不替代单元测试。

### 本地开发

前置：Python **3.12+**、Node.js **20+**、npm；可选 Docker。

**Linux / macOS：**

```bash
cp backend/.env.example backend/.env   # 填入 OPENAI_API_KEY
cp frontend/.env.example frontend/.env # 开发可保持 VITE_API_BASE 为空
./lorechat.sh setup
./lorechat.sh dev
```

**Windows：**

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
.\lorechat.bat setup
.\lorechat.bat dev
```

- 前端：http://localhost:5173
- 后端：http://localhost:8000

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

CI 在每次 push / PR 上跑同样的 backend pytest 与 frontend lint / test / build（见 `.github/workflows/ci.yml`）。

## Pull Request

1. 从最新 `master` 开分支，保持变更聚焦、可审查
2. 若改动用户可见行为或 API，请在 PR 描述中说明动机与验证方式
3. 涉及提示词：在描述中写明根因类别与验收意图（对照 AGENTS.md 清单）
4. 确保本地测试通过；勿在 PR 中附带个人知识库文件或密钥
5. 使用仓库提供的 PR 模板填写摘要与测试计划

Issue / 功能建议请使用 GitHub Issue 模板。安全问题请走 [SECURITY.md](SECURITY.md)，不要公开开 Issue。

## 许可证

贡献一经合并，即视为同意以项目 [MIT License](LICENSE) 授权。
