# 多文档合并：侧栏多选 + 草稿确认 + 可选删除原文

日期：2026-07-11  
状态：待实现

## 问题

知识库中存在多篇主题重叠的文档（如「漫剧工具盘点」「行业全景分析」等），用户希望一次性选中多篇，由模型全局重构合并为一篇。当前文件树仅支持单选预览，无批量整理入口；合并结果也不应直接覆盖原文。

## 目标

1. 侧栏支持多选文档（≥2 篇），一键触发合并。
2. **两阶段落库**：先生成**新文档草稿**供用户预览确认，确认后才正式写入知识库。
3. 确认入库后，**征询用户是否删除源文档**（默认不删，用户自选）。
4. 合并逻辑与现有会话归档一致：通读全文、按主题去重重组，禁止流水线拼接。

## 非目标

- 不支持合并到已有文档（首版一律新建；避免误覆盖）。
- 不做拖拽排序以外的复杂 diff 对比 UI。
- 不自动删除源文档。
- 不把合并任务塞入普通聊天流（独立动作，类似「沉淀」按钮）。

## 决策记录

| 项 | 决策 |
|----|------|
| 选文交互 | 侧栏「多选模式」开关 + 底部浮条 |
| 合并结果 | 始终新建文档 |
| 落库时机 | 草稿预览 → 用户确认 → 正式入库 |
| 原文处理 | 入库后征询；多选勾选要删的源文档，默认全不删 |
| 后端入口 | `Organizer.merge_documents` + `POST /api/docs/merge` |
| 草稿存放 | `.kb/drafts/{merge_id}.md`（不进检索，树中不可见） |

## 用户流程

```
多选 N 篇 → [合并为文档] → AI 生成草稿 → 右侧预览草稿
    → [确认入库] → 写入正式路径 → 征询是否删除源文档
    → 用户勾选 / 跳过 → 结束
```

### 阶段 0：多选

- 知识库标题栏增加 **「多选」** 切换按钮。
- 多选模式下：
  - 单击文件行 → 勾选/取消（不打开预览）。
  - 双击或行内 👁 → 仍可预览（不改变勾选状态）。
  - `Shift+单击` → 同文件夹内连续范围选择。
  - 文件夹右键（或行内菜单）→「全选此目录下文档」。
- 选中 ≥2 篇时，侧栏底部浮条：

  ```
  已选 4 篇  [查看列表 ▾]  [合并为文档]
  ```

- `Esc` 或再次点「多选」→ 退出多选，清空选择。
- 多选状态仅存于前端内存，刷新页面清空。

### 阶段 1：发起合并

点击「合并为文档」打开轻量配置面板（侧栏浮层或居中 Modal）：

| 字段 | 说明 |
|------|------|
| 已选列表 | 可拖拽排序（影响 AI 阅读顺序，后端仍按主题重组） |
| 补充说明 | 可选，如「保留各篇的数据表格」 |
| 建议标题 | 可选；留空则由 AI 生成 |

确认后调用 `POST /api/docs/merge`，侧栏浮条显示「合并中…」。

### 阶段 2：草稿预览

后端通读所选文档全文，调用 LLM 合并（规则同 `_DEFAULT_SUMMARY_RULES` + 多源文档场景），结果写入：

```
.kb/drafts/{merge_id}.md
```

响应含 `merge_id`、`draft_path`、`suggested_title`、`suggested_path`（正式入库建议路径）。

前端：

- 自动在右侧 DocViewer 打开草稿（`mode` 带 `draft` 标记）。
- 标题栏显示 **「合并草稿」** 徽标。
- 底部操作条（固定在 DocViewer 或浮于预览区）：

  ```
  [放弃]  [编辑后确认…]  [确认入库]
  ```

- **放弃**：删除草稿文件，关闭预览，回到多选（选择保留）。
- **确认入库**：见阶段 3。
- 草稿期间用户可在 DocViewer 内直接编辑正文（保存回草稿文件）。

### 阶段 3：确认入库

用户点「确认入库」→ `POST /api/docs/merge/{merge_id}/confirm`：

- 请求体可选 `{ rel_path?, title? }` 覆盖建议路径/标题。
- 将草稿移至正式知识库路径（`repo.write` + `indexer` 更新）。
- 删除 `.kb/drafts/{merge_id}.md`。
- 刷新侧栏；预览切换为正式文档。

### 阶段 4：征询删除源文档

入库成功后，在同一会话或独立确认卡片中展示 `PendingQuestion`（`multi_select: true`）：

> 合并文档已保存到《{path}》。是否删除以下源文档？

选项为源文档列表（checkbox，**默认全不勾选**）：

```
☐ 技术/AI内容创作/漫剧制作工具盘点.md
☐ 技术/AI内容创作/AI漫剧行业全景分析.md
☐ …
```

底部：

- **删除所选**（已选 N 项）
- **全部保留**（跳过，等价于不删）

删除走现有 `delete_kb` / `repo.delete` 逻辑；禁止删除 `系统/` 等受保护路径。

若用户关闭面板未操作，源文档保持不动；待确认项可稍后从对话时间线或 `/api/questions` 处理。

## 后端设计

### `Organizer.merge_documents`

```python
def merge_documents(
    self,
    source_paths: list[str],
    *,
    instruction: str = "",
    order: list[str] | None = None,
) -> MergeDraftResult:
```

1. 校验：`len(source_paths) >= 2`；路径存在且为 `.md`；不可含 `系统/`。
2. 按 `order` 或 `source_paths` 顺序 `repo.read` 全文。
3. `_synthesize_merge(sources, instruction)` — LLM 全局重构（非拼接）。
4. `_decide` 生成建议 `rel_path` / `title`（`action` 固定 `new`）。
5. 写入 `.kb/drafts/{uuid}.md`，frontmatter 记录：

   ```yaml
   draft: true
   merge_id: ...
   sources: [path1, path2, ...]
   created_at: ...
   ```

6. 返回 `MergeDraftResult(merge_id, draft_path, body, suggested_path, suggested_title)`。

### `_synthesize_merge` 提示词要点

- 输入：多篇文档全文 + 用户补充说明。
- 规则：与 `summarize_conversation` 相同——按主题组织、跨篇去重、冲突取新、剥离重复引言、禁止 `---` 堆叠多个一级标题。
- 输出：纯 Markdown 正文。

### API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/docs/merge` | body: `{ paths, instruction?, order? }` → 草稿 |
| GET | `/api/docs/merge/{id}` | 读草稿元数据 + 正文 |
| PUT | `/api/docs/merge/{id}` | 更新草稿正文（用户编辑后） |
| POST | `/api/docs/merge/{id}/confirm` | 正式入库 → 创建删除征询 |
| POST | `/api/docs/merge/{id}/discard` | 放弃草稿 |
| POST | `/api/docs/merge/{id}/resolve-sources` | body: `{ delete_paths: string[] }` 删除所选源文档 |

`confirm` 成功后通过 `PendingStore` 创建征询项，`payload` 含 `merge_id`、`new_path`、`source_paths`。

### 草稿与检索

- `.kb/drafts/` 目录：`list_tree` 与 `getTree` 均排除，不出现在侧栏。
- 草稿不写 FTS/向量索引。
- 正式入库后走正常 `indexer.index_file`。

## 前端改动范围

| 文件 | 改动 |
|------|------|
| `FileTree.tsx` | 多选模式：checkbox、shift 范围、双击预览 |
| `Sidebar.tsx` | 多选开关、底部浮条、合并配置面板 |
| `App.tsx` | `selectedPaths` 状态；草稿预览 path；与 `previewPath` 协调 |
| `DocViewer.tsx` | 草稿模式 UI：徽标、确认/放弃条；支持编辑保存草稿 |
| `api.ts` | merge 相关 API 封装 |
| `PendingQuestion.tsx` | 复用多选（源文档删除场景） |
| `index.css` | 多选行样式、浮条、草稿操作条 |

## 状态模型（App 层）

| 状态 | 类型 | 说明 |
|------|------|------|
| `selectionMode` | `boolean` | 是否处于多选模式 |
| `selectedPaths` | `Set<string>` | 已选文档路径 |
| `mergeDraftId` | `string \| null` | 当前合并草稿 ID |
| `previewPath` | 已有 | 预览路径；草稿用 `.kb/drafts/...` 虚拟路径或 API 直读 |

## 错误处理

| 场景 | 处理 |
|------|------|
| 少选（<2） | 「合并」按钮 disabled |
| 某源文件不存在 | 合并前校验，报错并列出缺失项 |
| LLM 失败 | 浮条提示，不创建草稿 |
| 确认时草稿已删 | 404，提示重新合并 |
| 删除时源文件已不存在 | 跳过并汇总提示 |

## 验收

1. 多选 4 篇同主题文档 → 合并 → 右侧出现草稿，结构清晰、无简单拼接痕迹。
2. 草稿可编辑 → 确认入库 → 侧栏出现新文档，可检索。
3. 源文档默认保留；征询中勾选 2 篇删除 → 仅删所选，其余保留。
4. 放弃草稿 → 知识库无新文档、无草稿残留。
5. 多选模式下单击不触发预览；双击可预览且不打乱勾选。
6. `系统/` 下文档不可选入合并列表。

## 后续可选增强（不在首版）

- 合并完成后自动退出多选模式。
- 聊天区同步展示源文档 chips（只读）。
- 合并历史记录（changelog 条目）。
