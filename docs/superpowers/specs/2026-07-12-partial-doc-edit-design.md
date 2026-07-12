# Agent 局部文档编辑（edit_doc）

日期：2026-07-12  
状态：复审修订（2026-07-12 架构审查后）  
前置文档：[2026-07-10-agent-tools-design.md](./2026-07-10-agent-tools-design.md)、[2026-07-11-system-layer-and-conversation-summary-design.md](./2026-07-11-system-layer-and-conversation-summary-design.md)、[2026-07-12-architecture-fixes.md](../plans/2026-07-12-architecture-fixes.md)（已实施）

## 0. 复审修订摘要（2026-07-12）

架构审查与修复实施后，本 spec 做如下调整：

| 原设计 | 修订 |
|--------|------|
| §9.2 《戒律》写完整 `edit_doc` 用法手册 | **改为 2 条策略规约**；API 契约放 Tool description + SYSTEM_PROMPT（与 `read_doc` 分层一致） |
| §6.5 写入后 `reindex_doc` 全量重索引 | **与 `edit_doc` 同期实现向量增量重索引**；FTS 仍全量重建（无 API 成本） |
| §8 错误反馈 | 强调 **结构化字段**（`error`/`status`/`applied`），禁止下游从 `summary` 散文解析（对齐 architecture-fixes B2） |
| §11 前端 | 复用已有 `KB_MUTATING_TOOLS`，加入 `edit_doc` |
| SYSTEM_PROMPT §7 | 小改走 `edit_doc`；语义融合才 `write_kb` + `target_path` |
| Phase 划分 | Phase 1 = `edits` + 增量向量重索引；`insert` 仍 Phase 2 |

## 1. 问题

### 1.1 现状

Agent 写入知识库的路径均为**整篇重写**：

| 路径 | 行为 | 问题 |
|------|------|------|
| `write_kb` + `target_path` | `Organizer._reorganize()` 将**全文 + 新片段**交给大模型，输出完整 Markdown | 大文档 token 成本高；易误改无关段落 |
| `summarize_conversation` | 全局重构 | 适合归档，不适合小改 |
| `PUT /api/doc`（前端手动） | 整篇 `body` 替换 | Agent 无对应工具 |

读取侧已有渐进式披露（`read_doc` 的 `offset` + 大纲 `@字符位置`），写侧缺少对称的**手术刀**能力。

### 1.2 目标

为 Agent 增加**局部修改**能力：改一段、补一句、修错别字时，只动目标区域，不重写整篇文档。

### 1.3 非目标

- 不采用 unified diff / `patch(1)` 格式（LLM 生成失败率高）。
- 不做跨文件原子事务。
- Phase 1 不做「自动判断该用 edit 还是 write」（靠 Prompt 分工）。
- 不改动 `write_kb` / `summarize_conversation` 的语义归置逻辑。
- Phase 1 不做前端 git diff 预览（可后续加）。

## 2. 行业调研结论

Cursor、Claude Code、Aider、Cline 等在「局部修改」上已收敛：

**精确字符串替换（search/replace）> unified diff > 整篇重写**

| 方案 | LLM 成功率 | 小改 token | 失败可恢复 | 适用 |
|------|-----------|-----------|-----------|------|
| search/replace | 高 | 低 | 高（未匹配则文件不变） | 改一段、补一句 |
| unified diff | 低 | 中 | 低 | 多文件原子 patch（代码库） |
| 整篇重写 | 中 | 高 | 低 | 新建、大规模重构 |

关键实践：

1. **先读后改**：未读取过的文件拒绝编辑。
2. **唯一性约束**：`old_string` 默认必须恰好出现 1 次（或显式 `replace_all`）。
3. **内容锚点，不用行号**：LLM 数行不准。
4. **分层匹配**：精确 → 换行归一化 → 行尾空白忽略（不做模糊 diff）。
5. **原子写入**：同一文件的多处 edits 在一个事务内顺序应用后一次 `write_doc`。
6. **可操作的错误信息**：未找到 / 歧义时返回上下文，便于模型自我纠正。

## 3. 方案选型

| 方案 | 说明 | 结论 |
|------|------|------|
| **A. 新增 `edit_doc`** | 与 `write_kb` 职责分离 | **采用** |
| B. 扩展 `write_kb` 加 `mode: patch` | 单工具双语义，参数组合爆炸 | 否决 |
| C. unified diff | LLM 失败率高 | 否决 |

## 4. 工具分层

```
READ_ONLY
  search_kb / read_doc / fetch_url / web_search

SURGICAL_WRITE（新增）
  edit_doc

SEMANTIC_WRITE（现有）
  write_kb / summarize_conversation / delete_kb / ask_user
```

### 4.1 选型指南（三层分工）

与架构审查确立的分层一致：

| 层级 | `edit_doc` 写什么 |
|------|------------------|
| **Tool description + parameters** | 必须先 `read_doc`；`old_string` 精确复制；`edits`/`insert` 参数含义 |
| **SYSTEM_PROMPT** | 工具清单一行 + 核心原则：改已有文档局部 → `edit_doc`；记新内容 → `write_kb`；归档 → `summarize_conversation`；**替换原 §7「write_kb 可传 target_path」的小改场景** |
| **《戒律》** | 仅 2 条**产品策略**（见 §9.2），不写 API 细节 |

| 用户意图 | 工具 |
|---------|------|
| 修改已有文档的局部内容（改字、改段、删段） | `edit_doc` |
| 在指定章节下追加段落 | `edit_doc`（insert 或 edits） |
| 对当前文档**补充新主题内容且需与全文语义融合** | `write_kb` + `target_path` |
| 随手记一条新内容 | `write_kb` |
| 归档整段会话 | `summarize_conversation` |
| 多文档合并成一篇 | 现有 merge API（非本 spec） |

**硬规则**：修改已有文档的**局部内容**时禁止用 `write_kb` 触发 `_reorganize` 整篇重组。

## 5. `edit_doc` 工具定义

### 5.1 Schema

```json
{
  "name": "edit_doc",
  "description": "对已有知识库文档做局部修改（替换或插入）。修改前必须先 read_doc 读取目标区域；old_string 必须从 read_doc 返回内容中精确复制。小范围修改优先于 write_kb。",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "文档相对路径，如 技术/docker/常用命令.md"
      },
      "edits": {
        "type": "array",
        "description": "按顺序应用的多处替换（同一文件原子提交）",
        "items": {
          "type": "object",
          "properties": {
            "old_string": {
              "type": "string",
              "description": "要被替换的原文（精确匹配，含换行）"
            },
            "new_string": {
              "type": "string",
              "description": "替换后的内容；删除内容时传空字符串"
            },
            "replace_all": {
              "type": "boolean",
              "description": "为 true 时替换所有匹配项，默认 false",
              "default": false
            }
          },
          "required": ["old_string", "new_string"]
        },
        "minItems": 1
      },
      "insert": {
        "type": "object",
        "description": "在指定位置插入内容（不删除原文）。与 edits 互斥。",
        "properties": {
          "after_heading": {
            "type": "string",
            "description": "在此 Markdown 标题行之后插入，如 '## 部署步骤'"
          },
          "at_offset": {
            "type": "integer",
            "description": "或在此字符偏移处插入（来自 read_doc 大纲 @位置）"
          },
          "content": {
            "type": "string",
            "description": "要插入的 Markdown 正文"
          }
        },
        "required": ["content"]
      }
    },
    "required": ["path"]
  }
}
```

### 5.2 参数约束

| 约束 | 值 | 说明 |
|------|-----|------|
| `edits` 与 `insert` | 互斥 | 每次调用只做一种操作 |
| 单次 `edits` 上限 | `max_edits=10` | 配置项，防失控 |
| 单段 `old_string` / `new_string` 上限 | `max_patch_chars=8192` | 超限返回错误 |
| `path` | 必须已存在 | 不存在返回 `NOT_FOUND`；本工具不创建新文件 |

### 5.3 定位机制

三层定位，由易到难：

1. **内容锚点（edits 主路径）**：`old_string` 含足够上下文（建议前后 2–3 行），确保唯一匹配。
2. **标题锚点（insert）**：`after_heading="## 部署步骤"` → 匹配标题行，在其后第一个换行处插入。
3. **字符偏移（insert 兜底）**：`at_offset=4820`（来自 `read_doc` 大纲 `@4820`）。

**不采用行号**：与 `read_doc` 字符偏移体系一致。

`insert` 定位优先级：`after_heading` > `at_offset`；二者都未提供时，默认追加到文档末尾。

## 6. 执行引擎

### 6.1 模块

新建 `backend/app/engine/patch.py`：

```python
@dataclass
class Edit:
    old_string: str
    new_string: str
    replace_all: bool = False

@dataclass
class Insert:
    content: str
    after_heading: str | None = None
    at_offset: int | None = None

@dataclass
class PatchError:
    code: str          # NOT_FOUND | AMBIGUOUS | INVALID | TOO_LARGE
    message: str
    hint: str | None = None
    occurrences: list[dict] | None = None  # AMBIGUOUS 时各匹配位置上下文

@dataclass
class PatchResult:
    ok: bool
    body: str | None
    applied: int
    message: str
    error: PatchError | None = None
    preview: str | None = None
    # 供增量重索引：在原文坐标系中，本次编辑触及的字符范围（合并所有 edits）
    affected_start: int | None = None
    affected_end: int | None = None

def apply_edits(body: str, edits: list[Edit], *, max_patch_chars: int) -> PatchResult: ...
def apply_insert(body: str, insert: Insert) -> PatchResult: ...
```

### 6.2 匹配策略（分层 fallback）

对每个 `old_string` 依次尝试：

1. **Pass 1**：字节级精确匹配。
2. **Pass 2**：换行符归一化（`\r\n` → `\n`）。
3. **Pass 3**：行尾空白忽略（逐行 rstrip 后比较）。

不做 diff-match-patch 模糊匹配：知识库文档宁可报错让模型重试，避免 silent 误改。

### 6.3 唯一性检查

```
count == 0  → NOT_FOUND（附最接近片段 hint）
count == 1  → 替换
count > 1 且 replace_all → 全部替换
count > 1 且非 replace_all → AMBIGUOUS（列出各 offset + 上下文）
```

多处 `edits` **顺序应用**：前一次替换会改变后续匹配的偏移；模型应提供互不重叠的锚点，或分多次 `edit_doc` 调用。

### 6.4 先读后改（read guard）

`ToolRegistry` 维护会话级已读集合：

```python
_read_guard: dict[str, set[str]]  # conversation_id → {path, ...}
```

- `read_doc` 成功 → 将 `path` 加入当前 `conversation_id` 集合。
- `edit_doc` 执行前 → `path` 必须在集合中，否则 `NOT_READ`。
- `edit_doc` 成功 → 路径保留在集合中（允许连续编辑）。
- 无 `conversation_id` 时（如 ingest 端点）→ 跳过 guard 或视为未读拒绝（与 ingest 模式一致：ingest 不走 `edit_doc`）。

### 6.5 写入流程

```
edit_doc(path, edits | insert)
  1. path 存在性检查（FileNotFoundError → NOT_FOUND）
  2. is_writable(path) 检查（.kb/、.git/ → PROTECTED）
  3. read guard 检查
  4. repo.read_doc(path) → body（记 old_body）
  5. apply_edits / apply_insert → new_body + affected_start/end
  6. repo.write_doc(path, meta, new_body, commit_msg=f"edit: {path}")
  7. indexer.reindex_doc_after_edit(path, old_body, new_body, affected_start, affected_end)
  8. repo.log_change(f"Agent 局部编辑 {path}")
  9. 返回 tool result（含结构化 error / applied / preview，见 §8）
```

**不走 Organizer**：局部编辑是确定性操作，不触发 `_decide` / `_reorganize`。

### 6.5.1 增量重索引（与 edit_doc 同期实现）

**问题：** 当前 `reindex_doc` 删除全文所有 chunk 并重新 `embed` 全部分块（`chunk_text` 默认 800 字 / 100 重叠）。大文档上 `edit_doc` 改一个字也会重嵌整篇，抵消「局部编辑省成本」的收益。

**策略：向量增量 + FTS 全量**

| 索引 | 策略 | 原因 |
|------|------|------|
| **向量（Chroma）** | 仅重嵌**受编辑影响的 chunk 及其之后**的分块 | `embed` 是主要成本 |
| **全文（FTS）** | 仍 `delete(doc_id)` + 全量 `add` | SQLite 本地操作，无 API 成本；表结构无 per-chunk id，部分更新收益低 |

**算法（`Indexer.reindex_doc_after_edit`）：**

1. `patch` 返回 `affected_start` / `affected_end`（原文坐标系，合并所有 edits 的最小覆盖区间）。
2. 对 `new_body` 用与 `chunk_text` 相同的参数计算全局 `chunk_starts[]`。
3. 找出**与 `[affected_start, affected_end]`（向两侧各扩 `overlap`）相交**的第一个 chunk 下标 `first_idx`。
4. **回退全量**（调用现有 `reindex_doc`）当：
   - `len(new_body) <= reindex_full_threshold`（默认 4000），或
   - `first_idx == 0` 且受影响区间 > 文档 50%，或
   - `affected_start` 为 None（insert 模式 Phase 2 再细化）
5. 否则：
   - `vector.delete_ids([f"{doc_id}::{i}" for i in range(first_idx, old_chunk_count)])`（需新增按 id 删除）
   - `tail_chunks = all_chunks[first_idx:]`，`embed(tail_chunks)`，按原 id 序号写回
   - `fulltext.delete(doc_id)` + `fulltext.add(doc_id, all_chunks)`（全量，便宜）

**新增/修改：**

- `app/index/chunk.py`：`chunk_starts(text) -> list[int]`，与 `chunk_text` 边界一致
- `app/index/vector.py`：`delete_ids(ids: list[str])`
- `app/index/indexer.py`：`reindex_doc_after_edit(...)` + 配置项 `reindex_full_threshold`

**共享：** `PUT /api/doc` 人工保存也可后续改用 `reindex_doc_after_edit`（传 `affected_start=0, affected_end=len` 等价全量），本 spec **不强制**，Phase 1 仅 `edit_doc` 走增量路径。

### 6.6 系统目录策略（已确认：选项 A）

`系统/戒律.md`、`系统/心法.md` **允许** `edit_doc` 编辑。

理由：

- 与 `repo.is_writable()` 一致（`protected_dirs` 仅禁止 `delete_kb`，不禁止写入）。
- 用户可通过对话调整行为规则，符合「系统控制层可见可编辑」设计。
- `SystemLayer` 按 mtime 缓存，编辑后下轮对话自动生效。

风险缓解：在 SYSTEM_PROMPT 与 Tool description 中写明「编辑系统/ 下文件前须 read_doc，改动最小化」；《戒律》仅保留策略级一句（见 §9.2）。

## 7. 工具注册与并行规则

```python
SURGICAL_WRITE_TOOLS = frozenset({"edit_doc"})
WRITE_TOOLS = frozenset({"write_kb", "delete_kb", "ask_user", "summarize_conversation", "edit_doc"})

# edit_doc 与 write_kb 一样必须串行，不可与写操作并行
def can_parallelize(tool_names: list[str]) -> bool:
    return all(n in READ_ONLY_TOOLS for n in tool_names)
```

`TOOL_LABELS` 新增：`"edit_doc": "局部编辑文档"`

## 8. 错误反馈（tool result）

**原则（architecture-fixes B2）：** tool result 必须带可机器读取的字段；`summary` 仅供人读，**禁止**下游用中文子串从 `summary` 推断状态。

成功：

```json
{
  "summary": "已在 技术/foo.md 应用 2 处修改（+47 字）",
  "sources": [{"type": "kb", "path": "技术/foo.md"}],
  "status": "saved",
  "applied": 2,
  "preview": "…修改点前后摘要…",
  "reindex_mode": "partial"
}
```

失败示例：

```json
{
  "summary": "编辑失败：old_string 在文档中出现 3 次",
  "sources": [],
  "status": "failed",
  "error": "AMBIGUOUS",
  "occurrences": [...],
  "suggestion": "请扩大 old_string 范围，包含更多唯一上下文"
}
```

`reindex_mode`: `"partial"` | `"full"`（调试用，可选）

错误码：

| code | 含义 |
|------|------|
| `NOT_READ` | 未先 read_doc |
| `NOT_FOUND` | 文档或 old_string 不存在 |
| `AMBIGUOUS` | old_string 多次出现 |
| `PROTECTED` | 路径不可写（.kb/ 等） |
| `INVALID` | edits 与 insert 同时提供、参数缺失等 |
| `TOO_LARGE` | 超出 max_edits / max_patch_chars |

## 9. Prompt 更新

### 9.1 `prompts.py` SYSTEM_PROMPT

- 工具清单增加 `edit_doc`（含先 read、old_string 精确复制等契约，与 Tool description 一致）。
- **修订 §7「当前查看的文档」**：
  - 改字/改段/删段 → `edit_doc`（可传 `path=active_doc`）
  - 补充新段落且需与全文语义融合 → `write_kb` + `target_path`
  - 全新随手记 → `write_kb`

### 9.2 《戒律》仅新增策略（不写 API）

```markdown
## 七、文档编辑
1. 已有文档的小范围修改不得触发整篇重组（用局部编辑通道，不用随手记合并通道）。
2. 修改 系统/ 下文件前应已确认当前内容，改动应最小化。
```

**不写入《戒律》的内容：** `old_string`、`edits` 参数、`read_doc` offset、insert 用法——这些属于 Tool + SYSTEM_PROMPT（同 §四渐进式披露与 `read_doc` 的分工）。

## 10. 配置项

```python
# config.py
edit_doc_max_edits: int = 10
edit_doc_max_patch_chars: int = 8192
edit_doc_require_read: bool = True   # 是否启用 read guard
reindex_full_threshold: int = 4000   # 低于此字符数或大面积改动时回退全量重索引
```

## 11. SSE / 前端

### 11.1 Phase 1（最小）

- `tool_result` 中 `tool === "edit_doc"` 时，时间线展示 summary（与 `write_kb` 类似）。
- 在已有 `KB_MUTATING_TOOLS`（`frontend/src/api.ts`）中加入 `"edit_doc"`，复用 `Chat.tsx` 侧栏刷新逻辑（architecture-fixes F1 已集中工具名常量）。

### 11.2 Phase 2（可选）

- 点击来源跳转文档并高亮 `preview` 片段。
- 展示 git diff（repo 已有 `.git`）。

## 12. 与现有能力的关系

| 能力 | 关系 |
|------|------|
| `write_kb` + `target_path` | 保留；语义融合场景仍走 `_reorganize` |
| `read_doc` offset / outline | `edit_doc` 定位的数据来源 |
| `PUT /api/doc` | 人工整篇编辑；Phase 1 仍用 `reindex_doc`；可后续接 `reindex_doc_after_edit` |
| `repo.append_doc` | 不暴露给 Agent；`insert` 模式覆盖追加场景 |
| merge API | 独立流程；本 spec 不改动 |

## 13. 文件结构

```
backend/app/
  config.py                    # 修改：edit_doc_* + reindex_full_threshold
  engine/
    patch.py                   # 新建：匹配与应用引擎（含 affected_start/end）
    agent/
      tools.py                 # 修改：edit_doc 注册与执行
      prompts.py               # 修改：工具说明 + §7 分工
      system_layer.py          # 修改：《戒律》§七 两条策略
  index/
    chunk.py                   # 修改：chunk_starts()
    vector.py                  # 修改：delete_ids()
    indexer.py                 # 修改：reindex_doc_after_edit()
backend/tests/
  test_patch.py                # 新建
  test_indexer.py              # 修改：增量重索引测试
  test_agent_tools.py          # 修改：edit_doc 集成测试
```

## 14. 测试计划

### 14.1 `test_patch.py`

- 精确替换成功
- 换行符归一化 fallback
- `NOT_FOUND`（0 次匹配）
- `AMBIGUOUS`（多次匹配）
- `replace_all`
- 多 edits 顺序应用
- `affected_start` / `affected_end` 正确合并
- 删除内容（`new_string=""`）
- `TOO_LARGE` 拒绝

### 14.2 `test_indexer.py`（增量重索引）

- 小编辑大文档：仅 tail chunks 被 re-embed（mock embed 调用次数或 spy delete_ids）
- 文档 < `reindex_full_threshold` → 全量路径
- 首 chunk 即受影响 → 全量回退
- FTS 仍全量更新且检索命中新内容

### 14.3 `test_agent_tools.py`

- 未 read 先 edit → `NOT_READ`
- read 后 edit 成功 → 文件内容变更 + 索引更新
- 保护路径 `.kb/` → `PROTECTED`
- `系统/戒律.md` 可编辑（选项 A）
- edits 与 insert 互斥校验
- tool result 含 `status`/`error` 结构化字段

### 14.4 `test_patch.py`（Phase 2）

- `insert` after_heading / at_offset / 文末默认

## 15. 实现阶段

### Phase 1（MVP，一并交付）

- `patch.py` + `edit_doc`（**edits 模式**）
- `PatchResult.affected_start/end` + **`reindex_doc_after_edit` 向量增量重索引**
- read guard
- Prompt / 《戒律》§七（仅策略）
- `KB_MUTATING_TOOLS` 加入 `edit_doc`
- 单元测试 + 索引测试 + Agent 工具测试

### Phase 2

- `insert` 模式（after_heading / at_offset）+ insert 的 affected 区间
- 前端 diff 预览
- `occurrences` / NOT_FOUND hint 优化
- `PUT /api/doc` 可选接入增量重索引

## 16. 决策记录

| 项 | 决策 |
|----|------|
| 编辑范式 | search/replace（非 unified diff） |
| 工具形态 | 独立 `edit_doc`（非扩展 write_kb） |
| 定位 | 内容锚点为主；insert 支持标题 / offset |
| 系统目录 | **允许编辑**（选项 A） |
| 是否走 Organizer | 否，直接 repo + reindex |
| read guard | 默认开启，per conversation |
| Prompt 分层 | API → Tool+SYSTEM_PROMPT；策略 → 《戒律》两条 |
| 重索引 | **向量增量 + FTS 全量**，与 Phase 1 同期 |
| tool result | 结构化 `status`/`error`，禁止散文解析 |
