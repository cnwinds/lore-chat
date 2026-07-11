# 系统控制层 + 会话总结重构 + 渐进式披露

日期：2026-07-11
状态：已实现

## 问题

1. **会话总结是"流水线拼接"**：系统没有独立的"会话总结"动作。落库由每轮 `write_kb` 触发，`organizer._reorganize` 每次只看到「已有文档全文 + 本轮片段」，是局部二路合并，从无全局视角。结果是多轮内容首尾相接（如两个 `#` 一级标题用 `---` 硬分隔），不符合"把整段会话重新梳理成一篇"的预期。
2. **缺少可控的"处世规则"层**：模型的行为规则散落在代码内置 `SYSTEM_PROMPT`，用户无法查看、编辑，也无法区分"已知问题的硬规则"与"未知问题的判断准则"。
3. **读取资料一次性全量注入**：`read_doc` 返回整篇正文、`fetch_url` 返回整页 markdown，长文档/网页直接占满上下文，无渐进式获取。

## 目标

1. **会话总结 = 全局重构**：通读整段会话（全部轮次 + 查到的依据），一次性去重、按主题重排、剥离对话痕迹，成文归档；而非逐轮拼接。
2. **抽出系统控制层**：两个提示词文件——《戒律》（已知问题的行为规约，可做/不可做）与《心法》（未知问题的处世准则）。二者驻留知识库、可见可编辑、**不参与检索**，但**每轮会话都注入为系统提示词**。
3. **会话可检索的生命周期**：未总结会话进入检索作为兜底；已总结则退位给总结文档。
4. **渐进式披露**：读取/抓取默认只取要点（≤3K），模型据此判断是否扩展、按需获取更多。

## 非目标

- 不自动归档：归档由用户主动触发（口令或按钮）。
- 会话不做向量索引（只做 FTS），避免每轮嵌入开销。
- 系统控制层文件不提供独立编辑器（复用现有文档读取；编辑可通过对话或直接改文件）。
- 不改动向量库结构。

## 决策记录

| 项 | 决策 |
|----|------|
| 落库模式 | 弱化逐轮落库，主靠会话末总结归档；显式"帮我记"仍走随手记 |
| 触发方式 | 口令 + 前端「归档会话」按钮 |
| 命名 | `系统/戒律.md`、`系统/心法.md` |
| 未总结会话索引 | 只进全文索引（FTS），零嵌入开销 |
| 渐进式披露范围 | `read_doc` + `fetch_url`（fetch 加抓取缓存）；首窗口附结构大纲；默认 3000 字 |

## 方案一：系统控制层（戒律 / 心法）

### 存放与可见性
- 目录 `系统/`（普通目录，`list_tree` 只跳过 `.kb/`，故树中可见）。
- 文件：`系统/戒律.md`（行为规约）、`系统/心法.md`（处世准则）。
- 首启若缺失，`SystemLayer` 用内置默认内容播种（含 frontmatter，走 git 提交）。

### 注入
- `build_system_prompt(mode, system_layer_text)` 分层拼接，优先级软→硬：
  **心法（处世哲学）→ 戒律（硬规约）→ 内置 SYSTEM_PROMPT（工具契约+事实铁律）→ 时间上下文 → 本轮 mode**。
- `AgentOrchestrator` 持有 `SystemLayer`，`run()` 开头 `compose()` 注入；按文件 mtime 缓存，编辑后自动生效。

### 不参与检索（三重保险）
1. 系统文件不经 `organizer`/`indexer`，本就不进 FTS/向量库；
2. `Retriever` 构造时传 `excluded_prefixes=("系统/",)`，命中即剔除；
3. `repo` 传 `protected_dirs=("系统",)`，`delete_kb` 禁止删除。

### 一处定义、两处使用
《戒律》的"会话总结"一节既是每轮系统提示词，又被总结动作直接引用为总结规则——改一次两处生效。

## 方案二：会话总结重构

### 触发
- 口令："总结/归档/整理这次会话""生成会话纪要" → 模型调 `summarize_conversation` 工具。
- 按钮：前端「归档会话」→ `POST /api/conversations/{cid}/summarize`。

### 流程
1. `ConversationStore.full_transcript(conv)`：整段会话稿（用户提问 + 助手结论 + 关键 web/kb 来源），不做轮次截断（仅总长兜底）。
2. `Organizer.summarize_conversation(transcript, hint_path, system_rules)`：
   - `_synthesize`：以《戒律》总结规则为系统提示词，用 `big` 模型通读全文 → 按主题去重重构 → 剥离对话痕迹 → 一篇 Markdown 正文。
   - 复用 `_decide` / `_normalize_decision` / `_apply_hint_path` 决定新建或并入相关文档；归档果断落库（`ambiguous` 强制降为 `new`，不打断用户）。
3. 归档成功后：`conversations.mark_summarized(cid, rel_path)` + `indexer.remove_conversation(cid)`。

### 反拼接硬规则（写入《戒律》与 `_reorganize` 提示词）
按主题而非发言/来源顺序组织；跨轮去重合并；禁止用 `---` 堆叠多个一级标题；全篇只有一套自洽标题层级。

## 方案三：会话检索生命周期

会话状态机：

```
新建 ──聊天──▶ [未总结·可检索(FTS)]
                  │ 归档
                  ▼
          生成总结文档(正常索引) + 会话移出索引
                  │
                  ▼
          [已总结·会话退出检索]
                  │ 归档后又追加消息
                  ▼
          [脏·会话重新可检索] ──再归档──▶ 已总结
```

- 会话对象新增字段：`summarized / summary_path / summarized_at / indexed_dirty`。
- `append_exchange` 后置 `indexed_dirty=True`；若此前已总结则复位 `summarized=False`。
- `/api/chat` 每轮结束后 `_reindex_conversation`：未总结 → `indexer.index_conversation`（FTS-only，doc_id `conv:{cid}`）；已总结 → 移出索引。
- `search_kb` 命中 `conv:` 来源时产出 `{type:"conversation", cid, excerpt}`，前端标为 💬「会话记录」。

## 方案四：渐进式披露

- 工具 `app/engine/disclosure.py`：`disclose(text, offset, limit, with_outline)` 返回窗口 + `total_chars/offset/returned_chars/has_more/next_offset`；`build_outline` 抽取标题及字符位置。
- `read_doc(path, offset=0, limit=3000)`：默认前 3000 字 + **首窗口附结构大纲**，可用 `offset`（或大纲中的 `@位置`）跳转/翻页。
- `fetch_url(url, offset=0, limit=3000)`：抓取结果按 url 缓存，`offset` 续读不重复抓取。
- 配置 `read_disclosure_chars=3000`；《戒律》新增「渐进式披露」一节：先取要点、善用大纲跳转、够了就停、勿一次灌满上下文。

## 实现范围

| 位置 | 改动 |
|------|------|
| `app/config.py` | `system_layer_dir/precepts_filename/soul_filename`、`read_disclosure_chars` |
| `app/engine/agent/system_layer.py`（新增） | `SystemLayer` 加载/播种/缓存/compose + 戒律/心法默认内容 |
| `app/engine/agent/prompts.py` | 分层注入；重写落库策略段；工具清单更新 |
| `app/engine/agent/orchestrator.py` | 注入系统层；透传 `conversation_id` 到工具 |
| `app/engine/agent/tools.py` | `read_doc` 窗口+大纲、`fetch_url` 缓存窗口、`summarize_conversation` 工具、会话来源 |
| `app/engine/disclosure.py`（新增） | 渐进式披露工具函数 |
| `app/engine/organizer.py` | `summarize_conversation` + `_synthesize` + 反拼接规则 |
| `app/engine/conversations.py` | 总结状态字段、`full_transcript`、`conversation_text`、`mark_summarized`、`clear_dirty` |
| `app/index/indexer.py` | `index_conversation`/`remove_conversation`（FTS-only） |
| `app/engine/retriever.py` | `excluded_prefixes` 过滤 |
| `app/storage/repo.py` | `protected_dirs` 保护系统目录 |
| `app/api/routes.py` | 归档端点、`/chat` 透传 cid + 会话重建索引 |
| `app/deps.py` | 装配 `SystemLayer`，传递保护/排除前缀，Container 增 `system_layer` |
| 前端 `api.ts`/`Chat.tsx`/`SourceChip.tsx`/`index.css` | `summarizeConversation` API、「归档会话」按钮、`conversation` 来源展示 |

## 验收

- 系统控制层：`系统/戒律.md`、`系统/心法.md` 出现在文档树；每轮系统提示词含二者；`search_kb` 不返回 `系统/`；`delete_kb` 无法删除；编辑后下一轮生效。
- 会话总结：口令与「归档会话」按钮均产出一篇全局重构、去重、无对话痕迹、单套标题层级的文档。
- 生命周期：未总结会话可被 `search_kb` 命中（来源为 conversation）；归档后会话移出索引、改由总结文档命中；归档后追加消息重新可检索。
- 渐进式披露：`read_doc` 首窗口 ≤3000 字且含大纲、`has_more/next_offset` 正确；`offset` 续读；`fetch_url` 续读不重复抓取。
- 测试：`test_disclosure.py`、`test_system_layer.py`、`test_summarize.py` 全通过；既有用例不回归（`test_ingest_auto_merges_when_related_exists` 为改动前既存 flaky，与本次无关）。
