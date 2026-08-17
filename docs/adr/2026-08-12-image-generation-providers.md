# ADR 2026-08-12：多厂商生图（ImageGen）能力层

## 状态

已采纳（2026-08-12）

## 背景

希望在聊天信息流与知识库文档中展示由模型生成的图片。智谱、百炼、OpenAI 等生图 HTTP 协议差异大（同步/异步、参数面、返回形态），不宜直接泄漏到 Agent 工具、时间线或 Markdown 内容层。

本仓库已有可对标的多厂商模式：联网搜索为 `Protocol` + backends + 有序链/冷却 failover；聊天模型链偏 OpenAI 兼容选模，与生图供给侧故障模型并不同构。

## 决策

### 1. 独立 ImageGen 能力层（deep module）

- **位置（拟定）**：`backend/app/engine/imagegen/`（providers 配置、router/failover、backends adapter、请求/结果契约）
- **对外**：稳定内部请求/结果；**不**把厂商 payload 传到聊天/文档层
- **不对齐**：不把生图候选塞进现有 chat/utility 模型链

### 2. 权威身份 = 本系统相对路径

- adapter 取得厂商 bytes/临时 URL 后，**立刻落盘**；对外只返回 KB 相对路径（或等价本系统引用）
- 厂商 CDN/OSS URL **不得**作为长期身份（易过期/鉴权失效）

### 3. Sink 由调用方指定

| destination | 行为 |
|---|---|
| `chat_attachment`（工具默认） | 写入 `媒体/生成/{YYYY-MM}/` + 自动文件名；路径挂到消息/工具结果的 `attachments` |
| `kb` | 经 `KnowledgeWriter` 按 `directory` + `filename` 写入二进制；返回相对路径供后续写 Markdown |

说明：聊天粘贴/附件图写入 `媒体/上传/{YYYY-MM}/`（内容哈希文件名，同图幂等）；生图默认进 `媒体/生成/{YYYY-MM}/`，与上传分轨、共用顶层「媒体」。权威身份仍是 KB 路径，复用 download / 签名等现有能力。

**路径勘误（2026-08-13）**：早期实现曾用 `generated/{YYYY}/` 与「未分类」承载聊天图；现统一为上表，启动时幂等迁移旧根并重写会话附件引用。

**路径勘误（2026-08-17）**：叶目录由 `{YYYY}` 改为 `{YYYY-MM}`（北京时间）。迁移 `media-layout-v2` 将 `generated/`、`未分类` 图片以及存量 `媒体/…/{年}/` 按文件 mtime 重分桶到 `{年月}`，并改写会话/Markdown 引用。

### 4. 第一期调用面：仅 Agent 工具

- 工具名拟定：`generate_image`
- HTTP/独立「生图按钮」**不做**第一期产品面；若后续需要，挂同一 ImageGen seam
- **执行语义**：工具调用内同步等待完成；厂商 submit+poll **封在 adapter 内**；可用现有 `tool_progress` 推状态
- **不做**：回合外异步 job、tool 先返回 `job_id` 再回调（留待真有长任务并行需求）

### 5. 展示协议

- **聊天**：
  - **主预览面**：时间线工具块（`generate_image` 完成且有 `attachments` 时默认展开并内联出图）
  - **消息级 `attachments`**：finalize 落库，保证重载/API 有权威路径列表；脚注只展示**未**出现在生图工具块中的路径（避免与主预览双份）
  - 正文若出现相对路径 `![](...)`，展示期可改写为 `/api/download`（不依赖模型必须写图链）
- **文档**：Markdown 源文件写相对路径 `![](...)`；**渲染期**重写为 `/api/download?path=...`（或等价鉴权 URL）。落盘时剥离 `/api/download` 绝对链，还原为相对路径。禁止把 API 绝对 URL 写进知识库正文

### 6. 多厂商配置与路由

- 设置形态对齐搜索链并扩展字段：有序列表项含 `id`、`provider`（`openai` / `zhipu` / `bailian`）、`api_key`、可选 `base_url`、`model`
- **同一 `provider` 可重复**（不同 `id`），以便配置同厂家的不同模型；唯一约束是 `id`
- **独立于**聊天模型设置；冷却 store 与 `model_cooldown` / `search_cooldown` **隔离**
- 运行时按序尝试；工具可选**弱覆盖**：优先尝试指定 provider/id，失败后仍可按链 failover 到其余条目（非主路径）
- **Failover 白名单**：仅 `transient`（超时/5xx/网络）与 `rate_limit` 可切下一家并冷却
- **不切换**：`safety` / `invalid_request` / `auth`（auth 记 disabled）/ `unknown`；非 `ImageGenError` 的意外异常映射为 `unknown` 后抛出，**不**切厂商
- adapter 将厂商错误映射到：`transient` / `rate_limit` / `auth` / `safety` / `invalid_request` / `unknown`

### 7. 内部请求契约（窄）

- 一等字段：`prompt`（必填）；可选 `aspect_ratio` 枚举（`1:1` / `16:9` / `9:16`，可再扩 `4:3` / `3:4`），默认 `1:1`
- 第一期 **固定 n=1**（不暴露多图，或钳制为 1）
- 风格、负面词、seed、厂商特有参数：不进工具主 schema；由提供商配置默认或日后 `options` 扩展
- 像素尺寸映射留在各 adapter

### 8. 第一期 adapter 范围

- 同时交付：`openai`、`zhipu`、`bailian` 三家薄 adapter

## 后果

- **正向**：上层（工具 / 时间线 / 文档）与厂商协议解耦；failover 与搜索同构，运维心智一致；KB 相对路径利于 git 与迁移
- **代价**：需维护错误分类映射表与尺寸映射表；三家第一期齐上，联调面较大
- **显式非目标（第一期）**：独立生图 UI、多图 `n>1`、回合外 job、把生图模型并入 chat 选模链、md 内嵌 data URL / 长期厂商热链
- **相关但独立**：会话深链 `conversation://` 属于聊天引用 UX，与 ImageGen 分 PR 交付

## 验收意图（根因同类，非孤例）

- 换一家厂商（协议不同）时，工具结果仍是本系统相对路径；聊天工具块可预览，消息级 attachments 落库可重载
- 写入文档的 md 仅为相对路径，Doc 预览能出图；换部署 host 不改 md 正文
- 模拟「审核拒绝」不触发切厂商；模拟「5xx/超时」可冷却并切下一家
- `destination=chat_attachment` 落在 `媒体/生成/{年月}/`；`destination=kb` 走 KnowledgeWriter 且路径符合 directory/filename 约定
