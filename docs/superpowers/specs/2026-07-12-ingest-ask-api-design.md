# `/ingest` 与 `/ask` 同步 API

**状态：** 保留（非废弃）  
**产品 UI：** 不使用；主入口为 `POST /api/chat`（SSE）  
**主要用途：** 自动化测试、脚本灌库、确定性集成调用

## 1. 定位

| 端点 | 一句话 |
|------|--------|
| `POST /api/ingest` | 强制落库：同步返回 `IngestResult`，语义等价于 Agent 必须调用 `write_kb` |
| `POST /api/ask` | 只读问答：同步返回 `{ text, sources, attachments }`，硬门禁止 `write_kb` |
| `POST /api/chat` | 产品主路径：SSE 时间线、会话持久化、策略由《戒律》+ 用户口令决定 |

**为何保留 ingest/ask：**

- **结果更确定**：固定 `mode`（`force_write` / `no_write`），不依赖模型是否「记得」落库策略。
- **效率更高**：同步 JSON，无需解析 SSE；测试灌库一条 `POST` 即可。
- **契约稳定**：`IngestResult` 自 MVP 延续，断言 `status` / `rel_path` 简单。

**为何不用于产品 UI：**

- 无时间线、无会话、无 `ask_user` 内嵌征询流程。
- 无 `web_enabled` 参数（默认不联网）；无 `active_doc_path`。
- 用户真实场景（边聊边记、归档、局部编辑）需 `/chat` 全工具链。

## 2. 请求与响应

### 2.1 `POST /api/ingest`

```json
{ "text": "docker ps 查看容器" }
```

→ `IngestResult`：

```json
{
  "status": "saved | rejected | question",
  "rel_path": "技术/docker/常用命令.md",
  "question_id": null,
  "message": "已保存到 …"
}
```

| status | 含义 |
|--------|------|
| `saved` | 已写入知识库 |
| `rejected` | 判定为纯提问（`organizer.is_question_only`），未写入 |
| `question` | 与已有文档歧义，需 `POST /api/questions/{id}/resolve` |

失败：Agent 未调用 `write_kb` → **502**。

实现：`routes._consume_agent_ingest` → `agent.run(..., mode=force_write)` → 取首个 `write_kb` 的 `tool_result` → `organizer.ingest_text`（与聊天内 `write_kb` 相同）。

### 2.2 `POST /api/ask`

```json
{ "query": "docker 怎么用" }
```

→

```json
{
  "text": "……",
  "sources": [ { "type": "kb", "path": "…", … } ],
  "attachments": [ "…/attachments/…" ]
}
```

实现：`routes._consume_agent_ask` → `agent.run(..., mode=no_write)` → 拼接 `text_delta`，`done` 时取 `sources`。

`select_tools(no_write)` **硬门移除** `write_kb`（不只靠 prompt）。

## 3. 与 Agent mode 的对应

定义见 `app/engine/agent/prompts.py`：

| mode | 常量 | 使用方 |
|------|------|--------|
| `default` | `MODE_DEFAULT` | `/chat` |
| `force_write` | `MODE_FORCE_WRITE` | `/ingest` |
| `no_write` | `MODE_NO_WRITE` | `/ask` |

`/ingest`、`/ask` 调用 `agent.run` 时：

- 不传 `conversation_id` / `history` / `active_doc_path`
- `web_enabled` 默认 `False`（仅本地检索 + `fetch_url`；与产品聊天默认一致）

## 4. 代码索引

| 位置 | 说明 |
|------|------|
| `backend/app/api/routes.py` | 端点与 `_consume_agent_*` |
| `backend/app/engine/agent/prompts.py` | mode 后缀 prompt |
| `backend/app/engine/agent/tools.py` | `select_tools` 硬门 |
| `backend/app/engine/organizer.py` | `ingest_text` 落库逻辑 |
| `backend/tests/test_api.py` | 集成测试（灌库 + 问答） |
| `frontend/src/api.ts` | `ingest()` / `ask()` 客户端（供脚本；UI 用 `chatStream`） |

## 5. 测试约定

- **灌库种子数据**：优先 `POST /api/ingest`，勿在测试里模拟 SSE `write_kb`。
- **只读召回 smoke**：`POST /api/ask` 或带 `conversation_id` 的 `/api/chat`（后者测时间线时用）。
- **歧义落库**：ingest 返回 `question` 后走 `/api/questions/{qid}/resolve`，不在 ingest 里轮询。

## 6. 与历史文档的关系

- Agent 化后 ingest/ask 经 Agent + mode；见 [agent-tools-design](./2026-07-10-agent-tools-design.md)。
- 端点**不废弃**；产品主入口是 `/api/chat`，本文档定位为机器 API。

## 7. 后续可选优化（未实现）

- 纯文本 ingest 直连 `organizer.ingest_text`（跳过 Agent LLM 轮次），含 URL 再走 Agent。
- `/ask` 增加可选 `web_enabled` 查询参数（与 `/chat` 对齐）。
- 不在此 spec 范围内改动产品 `/chat` 行为。
