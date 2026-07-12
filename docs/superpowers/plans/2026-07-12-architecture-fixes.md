# 架构审查修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development 或 superpowers:executing-plans 逐任务实现。步骤用 `- [ ]` 跟踪。所有代码步骤遵循 TDD：先写失败测试 → 跑失败 → 实现 → 跑通过 → 提交。

**Goal:** 修复 2026-07-12 全系统架构审查发现的分层混乱、散文状态解析、错误静默、配置不一致等问题，不改变对外功能行为。

**Architecture:** 分两条互不重叠的工作流并行——**后端流**（`backend/app/**`）与**前端流**（`frontend/src/**`）。后端流内部按文件依赖顺序串行；前端流独立。

**Tech Stack:** Python 3.11 / FastAPI / pytest；React + TypeScript + Vite。

**关联文档:** 本计划源自会话内的全系统审查（同日）。

---

## 决策记录（实现前已定）

| 项 | 决策 |
|----|------|
| `/ingest` 是否重写为直调 organizer | **否**。保留 Agent 驱动（需支持录入时抓 URL）；只修掉散文解析 |
| `Retriever.answer()` 是否删除 | **否**。仍被 `test_retriever.py` 使用 |
| `agent_max_tool_calls` 目标值 | **25**（code 与 `.env.example` 统一）；兼顾 read→edit 多步循环与成本上限 |
| 前端 God Component 大重构 | **本计划不做**（无测试、风险高）；仅做低风险健壮性修复，重构另立计划 |
| `mode` 魔法字符串 | 收敛为 `prompts.py` 常量，不引入 enum 依赖 |

---

# 后端流

## Task B1: 引入日志，消除静默吞异常

**Files:**
- Create: `backend/app/logging_config.py`
- Modify: `backend/app/index/indexer.py`
- Modify: `backend/app/api/routes.py`
- Modify: `backend/app/engine/retriever.py`

- [ ] **Step 1: 新建 `logging_config.py`**

```python
from __future__ import annotations

import logging

_LOGGER_NAME = "lorechat"


def get_logger(name: str | None = None) -> logging.Logger:
    base = logging.getLogger(_LOGGER_NAME)
    if not base.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        base.addHandler(handler)
        base.setLevel(logging.INFO)
    return base.getChild(name) if name else base
```

- [ ] **Step 2: 替换 `indexer.py` 的裸 `except: pass`**

`reindex_doc` 与 `remove_doc` 中：

```python
        except Exception:
            get_logger("indexer").warning("向量索引失败 doc_id=%s", doc_id, exc_info=True)
```

顶部 `from app.logging_config import get_logger`。保留兜底逻辑（不抛出），仅加日志。

- [ ] **Step 3: 替换 `routes.py` `_reindex_conversation` 的 `except: pass`**

```python
    except Exception:
        get_logger("routes").warning("会话重索引失败 cid=%s", cid, exc_info=True)
```

- [ ] **Step 4: 替换 `retriever.py` 向量检索的 `except: pass`**

`search()` 内：

```python
        except Exception:
            get_logger("retriever").warning("向量检索失败，回退全文", exc_info=True)
            vec_hits = []
```

- [ ] **Step 5: 运行**

```bash
cd backend && python -m pytest tests/test_indexer.py tests/test_retriever.py tests/test_api.py -q
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/logging_config.py backend/app/index/indexer.py backend/app/api/routes.py backend/app/engine/retriever.py
git commit -m "fix: log swallowed exceptions instead of silent pass"
```

---

## Task B2: write_kb 工具返回结构化状态，routes 停止散文解析

**问题:** `_ingest_from_write_kb_result`（routes.py:170）用 `"未写入"/"需要你确认"/"已保存"` 子串猜状态。`IngestResult` 本已有 `status`，但被 `_NON_SERIALIZABLE_KEYS` 剔除，routes 拿不到。

**Files:**
- Modify: `backend/app/engine/agent/tools.py`（`_write_kb` 输出结构化字段）
- Modify: `backend/app/api/routes.py`（`_ingest_from_write_kb_result` 读结构化字段）
- Test: `backend/tests/test_agent_tools.py`, `backend/tests/test_api.py`

- [ ] **Step 1: 写失败测试（tools 层）**

`test_agent_tools.py` 追加：

```python
@pytest.mark.asyncio
async def test_write_kb_exposes_structured_status(tmp_path):
    registry, repo, idx = _make_registry(tmp_path)
    result = await registry.execute("write_kb", {"text": "docker ps 查看容器列表"})
    assert result["status"] in {"saved", "question", "rejected"}
    if result["status"] == "saved":
        assert result["rel_path"]
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_agent_tools.py::test_write_kb_exposes_structured_status -q
```

Expected: FAIL（KeyError: status）

- [ ] **Step 3: 修改 `tools.py` `_write_kb`**

在返回 dict 中补结构化字段（不删 `ingest_result`）：

```python
        out: dict = {
            "summary": result.message,
            "sources": sources,
            "ingest_result": result,
            "status": result.status,
            "rel_path": result.rel_path,
        }
        if result.question_id:
            out["question_id"] = result.question_id
        return out
```

`status`、`rel_path` 是可 JSON 序列化的标量，会随 `_serialize_tool_output` 下发。

- [ ] **Step 4: 改 `routes.py` `_ingest_from_write_kb_result` 读结构化字段**

```python
def _ingest_from_write_kb_result(data: dict) -> dict:
    status = data.get("status")
    rel_path = data.get("rel_path")
    if not rel_path:
        sources = data.get("sources") or []
        rel_path = sources[0]["path"] if sources and sources[0].get("path") else None
    if status is None:
        # 兜底：老格式无结构化状态时按 rel_path 推断
        status = "saved" if rel_path else "rejected"
    return {
        "status": status,
        "rel_path": rel_path,
        "question_id": data.get("question_id"),
        "message": data.get("summary", ""),
    }
```

- [ ] **Step 5: 跑通过**

```bash
cd backend && python -m pytest tests/test_agent_tools.py tests/test_api.py -q
```

Expected: PASS（含现有 `test_ingest_rejects_question`、`test_ingest_then_ask`）

- [ ] **Step 6: Commit**

```bash
git add backend/app/engine/agent/tools.py backend/app/api/routes.py backend/tests/test_agent_tools.py
git commit -m "fix: pass structured write_kb status instead of parsing prose"
```

---

## Task B3: 征询问题类型改用结构化 kind，去掉子串猜测

**问题:** `_is_agent_question`（routes.py:469）用「多选」字样和 payload 缺字段来猜类型。

**Files:**
- Modify: `backend/app/api/routes.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: 确认现有 payload.kind 覆盖**

已知：`ask_user` 工具建的问题 payload `kind="agent"`（tools.py:443）；merge 建的 `kind="merge_sources"`；organizer ingest 歧义建的问题 payload 含 `decision`/`content`（无 kind）。

- [ ] **Step 2: 重写 `_is_agent_question` 为结构化判定**

```python
def _is_agent_question(q: dict) -> bool:
    payload = q.get("payload", {})
    kind = payload.get("kind")
    if kind == "agent":
        return True
    if kind == "merge_sources":
        return False
    # organizer 歧义确认问题带 decision/content，走 resolve_pending
    return not payload.get("decision") and not payload.get("content")
```

移除对 `q["multi_select"]` 和「多选」字样的依赖（multi_select 仍由 `resolve` 分支按 `body.choices` 走）。

- [ ] **Step 3: 跑现有征询相关测试**

```bash
cd backend && python -m pytest tests/test_api.py tests/test_merge_api.py -q
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes.py
git commit -m "fix: classify pending questions by payload kind not text matching"
```

---

## Task B4: 会话总结/重组规则单一来源

**问题:** 同一套「按主题去重、禁止拼接」规则在 4 处重复（《戒律》二、`_DEFAULT_SUMMARY_RULES`、`_synthesize` user prompt、`_reorganize` system prompt），改《戒律》不全生效。

**Files:**
- Modify: `backend/app/engine/organizer.py`
- Test: `backend/tests/test_summarize.py`, `backend/tests/test_organizer.py`

- [ ] **Step 1: `_DEFAULT_SUMMARY_RULES` 明确标注为 fallback**

改注释，不改内容：

```python
# 仅当《戒律》缺失/读取失败时的兜底规则；正常运行以 system_rules（《戒律》二）为准。
_DEFAULT_SUMMARY_RULES = (
    ...
)
```

- [ ] **Step 2: `_synthesize` 的 user prompt 删除重复规则句**

将 user 消息中重复的「按主题而非发言顺序组织，跨轮去重合并，冲突以更新信息为准 / 剥离对话痕迹」等改为引用式，不再复述规则细则：

```python
            {
                "role": "user",
                "content": (
                    "以下是完整会话记录。请严格按上述规约通读全文后产出归档文档正文；"
                    "只输出正文 Markdown，不要 frontmatter，不要用代码围栏包裹全文。\n\n"
                    f"=== 会话记录 ===\n{transcript}"
                ),
            },
```

规则细则只保留在 system 消息（`rules`，来自《戒律》）。

- [ ] **Step 3: `_reorganize` system prompt 引用同一套「反拼接」精神**

在 `_reorganize` 的 system 内容里，把「去重、归类，不要简单拼接」替换为与总结一致的措辞，并加一行注释指明其与《戒律》总结规则同源、后续应考虑统一注入：

```python
                    "1. 通读已有文档与新内容，按主题去重合并，禁止简单拼接（与会话总结规约一致）\n"
```

（本任务不强行合并两条 LLM 调用，仅消除措辞漂移与重复规则源。）

- [ ] **Step 4: 跑总结/组织测试**

```bash
cd backend && python -m pytest tests/test_summarize.py tests/test_organizer.py tests/test_merge_documents.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/organizer.py
git commit -m "refactor: single source for summary/reorganize rules"
```

---

## Task B5: 配置统一与魔法值收敛

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/app/engine/retriever.py`
- Modify: `backend/app/engine/agent/prompts.py`
- Modify: `backend/app/deps.py`（若 retriever 需读 settings 阈值）
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: `config.py` 对齐 `agent_max_tool_calls` 并新增检索阈值**

```python
    agent_max_tool_calls: int = 25
    ...
    # 向量检索余弦相似度下限
    min_vector_score: float = 0.45
```

- [ ] **Step 2: `.env.example` 同步**

```env
AGENT_MAX_TOOL_CALLS=25
MIN_VECTOR_SCORE=0.45
```

- [ ] **Step 3: `retriever.py` 阈值改为可注入**

构造函数加 `min_score: float = 0.45`，用 `self.min_score` 替换模块级 `MIN_VECTOR_SCORE`（保留模块常量作默认）。`deps.py` 构造 Retriever 时传 `min_score=settings.min_vector_score`。

- [ ] **Step 4: `prompts.py` mode 常量化**

```python
MODE_DEFAULT = "default"
MODE_FORCE_WRITE = "force_write"
MODE_NO_WRITE = "no_write"
```

`build_system_prompt` 内与 routes/orchestrator 调用处改用常量（routes.py、orchestrator 若引用则一并改）。

- [ ] **Step 5: `test_config.py` 补断言**

```python
    assert s.agent_max_tool_calls == 25
    assert s.min_vector_score == 0.45
```

- [ ] **Step 6: 跑测试**

```bash
cd backend && python -m pytest tests/test_config.py tests/test_retriever.py tests/test_api.py -q
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/config.py backend/.env.example backend/app/engine/retriever.py backend/app/engine/agent/prompts.py backend/app/deps.py backend/tests/test_config.py
git commit -m "fix: align agent tool-call cap and lift magic constants to config"
```

---

## Task B6: 封装修复 + active_doc_path 结构化注入

**Files:**
- Modify: `backend/app/storage/repo.py`（公开 abs 方法）
- Modify: `backend/app/api/routes.py`（upload 用公开方法）
- Modify: `backend/app/engine/agent/orchestrator.py`（active_doc_path 独立系统消息）
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: `repo.py` 增加公开方法**

```python
    def abs_path(self, rel_path: str) -> Path:
        return self._abs(rel_path)
```

`routes.py:329` 改 `c.repo.abs_path(rel)`。

- [ ] **Step 2: `orchestrator.py` 用独立消息传递当前文档**

将：

```python
        if active_doc_path:
            user_text = f"{user_text}\n\n[用户当前正在查看文档：{active_doc_path}]"
```

改为在 messages 里追加一条独立 system 提示（不污染 user_text）：

```python
        messages: list[dict] = [
            {"role": "system", "content": build_system_prompt(mode, system_layer_text)},
        ]
        if active_doc_path:
            messages.append({
                "role": "system",
                "content": f"[上下文] 用户当前正在查看文档：{active_doc_path}",
            })
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_text})
```

删除原 user_text 拼接。

- [ ] **Step 3: 跑测试**

```bash
cd backend && python -m pytest tests/test_api.py tests/test_agent_orchestrator.py -q
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/storage/repo.py backend/app/api/routes.py backend/app/engine/agent/orchestrator.py
git commit -m "fix: public repo path api and structured active-doc context"
```

---

## Task B7: 后端全量回归

- [ ] **Step 1:**

```bash
cd backend && python -m pytest -q
```

Expected: 全部 PASS。若有失败，定位到对应 Task 修正后重跑。

---

# 前端流（低风险健壮性修复，不做大重构）

## Task F1: 工具名常量与 KB 变更工具集中定义

**问题:** `"write_kb"/"delete_kb"` 等硬编码散落 `Chat.tsx`、`TimelineBlockView.tsx`、`api.ts`；`TOOL_LABELS` 与后端不同步（缺 `delete_kb`、`summarize_conversation`）。

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: 在 `api.ts` 定义单一来源**

```typescript
export const TOOL_LABELS: Record<string, string> = {
  search_kb: "检索本地知识库",
  read_doc: "读取文档",
  fetch_url: "打开链接",
  web_search: "搜索网页",
  write_kb: "整理到知识库",
  summarize_conversation: "归档整段会话",
  delete_kb: "删除知识库内容",
  ask_user: "征询用户",
};

// 会改动知识库、需要刷新侧栏的工具
export const KB_MUTATING_TOOLS = ["write_kb", "delete_kb", "summarize_conversation"] as const;
```

- [ ] **Step 2: `Chat.tsx` 用集合判定，替换硬编码 if**

将 `data.tool === "write_kb"` / `"delete_kb"` 分支改为：

```typescript
          if ((KB_MUTATING_TOOLS as readonly string[]).includes(data.tool as string)) {
            onKbChanged?.(kbPathFromToolResult(data));
          }
```

（`summarize_conversation` 无 path 时 `kbPathFromToolResult` 返回 undefined，语义正确。）

- [ ] **Step 3: 构建校验**

```bash
cd frontend && npm run build
```

Expected: 构建通过

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api.ts frontend/src/components/Chat.tsx
git commit -m "refactor: centralize tool labels and kb-mutating tool set"
```

---

## Task F2: SSE 解析健壮化

**问题:** `api.ts` 流解析 `r.body!` 非空断言、`JSON.parse` 无 try/catch、尾帧丢弃、未知事件静默。

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: 加空 body 检查与 JSON 容错**

在读取流的生成器起始：

```typescript
  if (!r.body) {
    throw new Error("响应缺少可读流");
  }
  const reader = r.body.getReader();
```

解析每个事件块处，`JSON.parse` 包 try/catch：

```typescript
        try {
          yield {
            event: eventLine.slice(7).trim(),
            data: JSON.parse(dataLine.slice(6)) as Record<string, unknown>,
          };
        } catch (err) {
          console.warn("跳过无法解析的 SSE 事件", err, dataLine);
        }
```

- [ ] **Step 2: flush 尾部残留 buffer**

读取循环 `done` 后，对 buffer 中剩余的完整事件块做一次解析（若存在 `event:`+`data:`）。若现有实现按 `\n\n` 切分，确保最后一段非空也被处理。

- [ ] **Step 3: 构建**

```bash
cd frontend && npm run build
```

Expected: 通过

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api.ts
git commit -m "fix: robust SSE parsing (null body, JSON errors, tail flush)"
```

---

## Task F3: 修复 TimelineBlockView 模块级 Map 泄漏

**问题:** `TimelineBlockView.tsx:57` `toolBlockOpenOverride` 模块级 Map 永不清理、跨会话共享。

**Files:**
- Modify: `frontend/src/components/TimelineBlockView.tsx`

- [ ] **Step 1: 改为按会话隔离或组件内 state**

首选：将展开状态提升为组件内 `useState`（随组件卸载回收）。若必须跨渲染保留，改用带上限的 LRU 或以 `conversationId+blockId` 为 key 并在会话切换时清理。实现时选组件内 `useState` 方案（最简、无泄漏）。

- [ ] **Step 2: 构建**

```bash
cd frontend && npm run build
```

Expected: 通过；手动验证工具块展开/折叠仍工作。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TimelineBlockView.tsx
git commit -m "fix: scope timeline block open-state to component, drop leaking module map"
```

---

# 不在本计划内（另立计划）

| 项 | 原因 |
|----|------|
| 前端 `DocViewer`/`Chat`/`App` God Component 拆分 | 无测试、体量大、风险高，需独立重构计划 |
| 前后端时间线状态机双实现合并 | 需先定义共享 schema，跨端改动大 |
| `edit_doc` 全量重索引 → 增量重索引 | 属 partial-doc-edit Phase 2 |
| `/ingest`、`/ask` 端点重构 | 涉及产品行为取舍，需单独确认 |

---

## Spec 覆盖自检

| 审查问题 | 对应 Task |
|---------|-----------|
| 会话总结规则 4 份复制 | B4 |
| 散文子串反推状态（ingest） | B2 |
| 散文子串反推状态（question kind） | B3 |
| 错误静默吞掉 | B1 |
| `agent_max_tool_calls` 冲突 | B5 |
| `MIN_VECTOR_SCORE` 魔法值 | B5 |
| `mode` 魔法字符串 | B5 |
| `repo._abs` 封装破坏 | B6 |
| `active_doc_path` 散文注入 | B6 |
| 工具名硬编码 / TOOL_LABELS 不同步 | F1 |
| SSE 解析不健壮 | F2 |
| TimelineBlockView Map 泄漏 | F3 |
