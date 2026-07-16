# 部署就绪：登录门禁、知识库导入导出、配置热更新

日期：2026-07-16  
状态：设计已确认，待实施计划  
前置：当前产品为单机可用的 Lore Chat（FastAPI + React + Docker/Nginx），无鉴权、无导入导出、无配置界面。

## 1. 目标

为服务器部署补齐三块能力，使实例可安全对外开放、可迁移、可在界面调参：

1. **单用户登录门禁**：首次访问设置管理员密码；之后必须登录才能使用 API 与界面。
2. **知识库导出/导入**：支持完整迁移（文档、会话、记忆、系统层、不可重建的 `.kb` 状态）；FTS/向量索引不打包，导入后重建。
3. **配置界面 + 全量热更新**：登录后可改运行参数并立即生效，无需重启进程；`KB_PATH` 不可改。

非目标（本期不做）：

- 多用户账号、角色、多租户
- 增量/按文档挑选式合并导入
- 远程配置中心、多环境配置切换
- 运行时热切换 `KB_PATH`

## 2. 已确认决策

| 项 | 决策 |
|----|------|
| 用户模型 | 单用户共享管理员密码（门禁，非多账号） |
| 密码初始化 | 首次访问引导页设置密码（setup） |
| 会话 | HttpOnly Cookie Session；拦全部 `/api/*`（含 SSE） |
| 导出范围 | 完整可迁移；排除可重建的 FTS/向量索引 |
| 导入模式 | `empty_only` 与 `overwrite` 均支持，用户显式选择 |
| 覆盖导入 | 先自动备份现有库，再清空并导入；失败尽量回滚 |
| 配置热更新 | 除 `KB_PATH` 外，可编辑项全部热更新 |
| 配置持久化 | `KB_PATH/.kb/settings.json`，优先于同名 env |
| 密码存储位置 | `KB_PATH/.kb/auth.json`；随导出迁移 |

## 3. 架构总览

```
浏览器 ── Cookie Session ──▶ Nginx (SPA + /api 反代)
                                │
                                ▼
                           FastAPI
                    ┌───────────┼───────────┐
                    │           │           │
              AuthMiddleware  SettingsStore  Backup/Import
                    │           │           │
                    └───────────┼───────────┘
                                ▼
                         KB_PATH
                    ├── **/*.md + attachments
                    ├── 系统/
                    ├── .git/
                    └── .kb/
                        ├── auth.json
                        ├── settings.json
                        ├── conversations/
                        ├── memory/
                        ├── workspace.json / pending / merge / …
                        └── index/   ← 可重建，导出排除
```

新增后端模块（建议落点）：

| 模块 | 职责 |
|------|------|
| `auth` | 密码哈希读写、session、setup/login/logout/change-password、依赖注入 |
| `settings_store` | env 默认 + `settings.json` 合并；保存；热替换 LLM/Embed/Search 客户端 |
| `backup` | 导出 zip、覆盖前备份、导入解压、回滚 |
| `maintenance_lock` | 导入/导出期间写锁 |
| `reindex` 任务 | 导入后异步重建索引；可手动触发 |

前端：`Setup/Login` 门页；壳内 `Settings`（配置分组、改密、导入导出、重建索引入口）。

## 4. 登录与会话

### 4.1 密码

- 路径：`{KB_PATH}/.kb/auth.json`
- 字段：`password_hash`（bcrypt）、`updated_at`
- 无此文件或未设密 → `setup_required: true`

### 4.2 API

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/auth/status` | 无 | `{ setup_required, authenticated }` |
| POST | `/api/auth/setup` | 无，且仅 setup_required | body: `{ password }`；成功后签发 session |
| POST | `/api/auth/login` | 无 | body: `{ password }` → Set-Cookie |
| POST | `/api/auth/logout` | 需登录 | 清 session |
| POST | `/api/auth/change-password` | 需登录 | body: `{ old_password, new_password }` |

公开白名单：**仅** `status` / `setup` / `login`。其余 `/api/*`（含 `/api/chat` SSE）必须已登录，否则 `401`。

### 4.3 Session

- HttpOnly、SameSite=Lax、Path=/；生产建议 Secure（HTTPS）
- 建议滑动过期默认 7 天（可用 settings 或 env 调）
- 实现可选：服务端 session 表（`.kb/sessions.db` 或内存+文件）或签名 cookie；推荐服务端 session id，便于强制登出

### 4.4 前端门禁

- 启动先调 `status`
- `setup_required` → 设密页；未登录 → 登录页；已登录 → 现有 AppShell
- 任意 API `401` → 清本地状态并回登录页
- `fetch` 使用 `credentials: 'include'`

### 4.5 安全

- CORS 从 `*` 收紧为同源（Docker Nginx 同域）
- 不做多用户；密码与 session 不进聊天索引
- `auth.json` 随导出带走 → 迁移后同一密码

## 5. 知识库导出 / 导入

### 5.1 导出包

格式：`.zip`，根目录含 `manifest.json`。

**包含**

- 全部 Markdown（含 `系统/`）与附件
- `.git/`（文档演进历史）
- `.kb/` 中不可重建部分：`conversations/`、`memory/`、`workspace.json`、`pending.json`、`merge_sessions.json`、`changelog.md`、`migrations/`、`auth.json`、`settings.json` 等

**排除**

- `.kb/index/vec/`
- `.kb/index/fts.db`、`conversation_fts.db` 及同类 FTS/向量缓存
- 临时文件（`*.db-wal` / `*.db-shm` 在打包前应先 checkpoint 或拷贝一致快照）

`manifest.json` 至少含：`format_version`、`exported_at`、`app`、包含项标志、源 `workspace_id`（若有）。

### 5.2 导出 API

- `GET /api/admin/export`（需登录）→ `application/zip` 下载
- 导出期间持写锁（或等价只读窗口），避免半写入包
- 大库注意超时：Nginx 已有较长 proxy timeout；流式写 zip 到响应

### 5.3 导入 API

- `POST /api/admin/import`（需登录）
  - multipart：`file`（zip）、`mode`：`empty_only` | `overwrite`
- **empty_only**：目标库非空 → `409`，不改动  
  - **空库判定（显式）**：不存在任何会话记录，且除允许的默认骨架外无用户文档/附件。默认骨架仅限：空的或仅含初始化结构的 `.kb/`、可选的空 `.git/`、以及系统层模板文件（若产品启动时自动创建）。只要存在用户创建的分类目录文档、附件、或 `conversations.db` 中有会话，即视为非空。
- **overwrite**：
  1. 对当前 `KB_PATH` 打自动备份 zip
  2. 备份存到 `{KB_PATH 的父目录}/lorechat-backups/`（Docker 建议额外 volume 或挂在数据盘旁，避免写进将被清空的目录内）
  3. 清空 `KB_PATH` 内容并解压导入包
  4. 重新挂载存储/打开 DB
  5. 异步重建索引
- 导入中持全局写锁；聊天/写文档返回明确「维护中」错误码

### 5.4 失败与回滚

- `empty_only` 失败：目标不变
- `overwrite` 在清空之后、解压完成之前失败：从自动备份回滚；回滚失败 → 错误响应携带备份文件路径，人工介入
- 索引重建失败：数据已可用，搜索降级；提供 `POST /api/admin/reindex` 手动重试

### 5.5 边界

- 不做文档级 merge 导入
- 导入包 `format_version` 不兼容时拒绝并说明

## 6. 配置界面与热更新

### 6.1 分层

| 类型 | 来源 | 界面 |
|------|------|------|
| 部署级只读 | 进程 env（如 `KB_PATH`） | 只读展示 |
| 可热更运行配置 | `.kb/settings.json` 覆盖 env 默认 | 可编辑 |

可热更范围：现有 `Settings` 中除 `kb_path` 外的运行项（模型、Base URL、API Key、检索、Agent、搜索 Provider、记忆维护间隔等）。`system_layer_dir` 等路径类字段若改动风险高，默认仍允许热更新但校验非空；**唯独 `kb_path` 禁止写入**。

### 6.2 合并规则

1. 启动：`BaseSettings` 读 env / `backend/.env` 作为默认
2. 若存在 `.kb/settings.json`，同名字段覆盖默认
3. 保存：只把「可编辑且用户提交的字段」写入 `settings.json`（原子写：写临时文件再替换）
4. `reload()`：更新内存 Settings → 重建 OpenAI / Embed / Search 等依赖客户端并挂回 container

进行中的 SSE 请求继续使用请求开始时绑定的客户端；新请求用新配置。

### 6.3 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/settings` | 当前生效配置；密钥脱敏（如保留 last4） |
| PUT | `/api/admin/settings` | 校验 + 持久化 + 热更新；字段级错误 |

改密不走 settings，走 `/api/auth/change-password`。

### 6.4 前端设置页

- 入口：侧栏或顶栏「设置」
- 分组：模型与路由、API 密钥、检索、Agent、搜索、记忆维护
- 同页区块：导出、导入（模式选择 + 覆盖确认文案）、改密、重建索引
- 密钥：默认脱敏；点「修改」后清空再输入；未改的密钥字段 PUT 时用哨兵或省略表示「保持原值」

### 6.5 安全注意

- `settings.json` 含明文密钥，依赖登录门禁与 HTTPS
- 导出包含 `settings.json` 与 `auth.json` → 备份文件需当作机密保管

## 7. 前端与部署衔接

- 现有无 Router：用壳状态切换 `setup | login | app`；设置用面板/抽屉，不必上完整路由库
- Nginx：保持同域 SPA + `/api`；确保 Cookie 路径与反向代理头正确
- Docker：`KB_PATH=/data/knowledge` 不变；建议增加 backups 目录挂载（如 `/data/backups`）
- 健康检查：若现用未鉴权 `GET /api/tree`，改为公开 `GET /api/health`（或允许探活免登），避免编排误杀

## 8. 错误码约定（建议）

| HTTP | 场景 |
|------|------|
| 401 | 未登录 |
| 403 | 已设密仍调 setup；或维护锁拒绝写 |
| 409 | empty_only 但库非空；format 冲突 |
| 422 | 校验失败（密码过短、非法 URL 等） |
| 503 | 导入导出锁定期间的写请求（或专用 409 + code） |

响应 JSON 带稳定 `code` 字段，便于前端文案。

## 9. 验证要点

- 未设密只能 setup；设密后 setup 返回错误；错误密码无法登录
- 未登录访问 `/api/tree`、`/api/chat` → 401；登录后 Cookie 可 SSE 聊天
- 导出 zip 不含 vec/fts；含 md、conversations、memory、auth、settings
- 空库 `empty_only` 成功并触发重建；非空 `empty_only` 拒绝且数据不变
- 非空 `overwrite`：先出现备份文件，再变为导入内容；故意失败时可回滚
- 修改 API Key / 模型后，**新**对话立即使用新配置，进程未重启
- `KB_PATH` 在 GET 可见、PUT 无法修改

## 10. 实施顺序建议

1. Auth（门禁 + 前端登录/设密）—— 部署安全底线  
2. SettingsStore + 设置 API/UI + 热更新  
3. Export/Import + 写锁 + 备份回滚 + 重建索引  

三者可同一里程碑交付，但按上述顺序合入，便于分步验证。
