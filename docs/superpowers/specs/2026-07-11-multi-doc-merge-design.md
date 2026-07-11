# 多文档合并：侧栏多选 + 直接成文 + 满意/不满意分流

日期：2026-07-11  
状态：已实现（v2）  
实现计划：[2026-07-11-multi-doc-merge.md](../plans/2026-07-11-multi-doc-merge.md)

## 问题

知识库中存在多篇主题重叠的文档，用户希望一次性选中多篇，由模型全局重构合并为一篇。当前文件树仅支持单选预览，无批量整理入口。

## 目标

1. 侧栏支持多选文档（≥2 篇），一键触发合并。
2. 合并结果**直接写成知识库中的一篇新文档**（无独立草稿区、无二次「确认入库」）。
3. 用户在预览区判断满意与否：
   - **满意** → 保留新文档 → 征询是否删除源文档。
   - **不满意** → 删除新文档，或**重新生成并覆盖**同一篇。
4. 合并逻辑与现有会话归档一致：通读全文、按主题去重重组，禁止流水线拼接。

## 非目标

- 不引入 `.kb/drafts/` 或任何「草稿」概念与 API。
- 不支持合并到已有文档（首版一律新建）。
- 不自动删除源文档或新文档。
- 不把合并任务塞入普通聊天流。

## 决策记录

| 项 | 决策 |
|----|------|
| 选文交互 | 侧栏「多选模式」+ 底部浮条 |
| 合并结果 | 始终新建一篇正式文档，立即可在侧栏看到 |
| 不满意处理 | 「删除此文」或「重新生成」（覆盖同一路径） |
| 危险操作确认 | **仅当用户改过正文**时，「重新生成」「删除此文」才弹确认；未改则直接执行 |
| 满意后 | 保留新文档 → 征询是否删除源文档（多选，默认不勾） |
| 会话追踪 | `.kb/merge_sessions.json` 记录 pending 合并会话（非草稿文件） |
| 改动检测 | 会话存 `generated_content_hash`；对比当前文件正文 hash 判断是否被改过 |
| 后端入口 | `Organizer.merge_documents` + merge API |

## 用户流程

```
多选 N 篇 → [合并为文档] → AI 直接写入新文档 → 右侧预览
    ├─ 满意 → [采用] → 征询是否删除源文档 → 结束
    └─ 不满意 → [删除此文] 或 [重新生成]
                    ├─ 删除此文：删新文档，原文不动，结束
                    └─ 重新生成：覆盖新文档正文，继续预览判断
```

### 阶段 0：多选（不变）

- 知识库标题栏 **「多选」** 开关。
- 多选模式：单击勾选；双击 / 👁 预览；`Shift+单击` 范围选择；文件夹「全选此目录」。
- 选中 ≥2 篇时侧栏底部浮条：`已选 N 篇 · [合并为文档]`。
- `Esc` 退出多选并清空选择。

### 阶段 1：发起合并

轻量配置面板：

| 字段 | 说明 |
|------|------|
| 已选列表 | 可拖拽排序（影响 AI 阅读顺序） |
| 补充说明 | 可选 |
| 建议标题 | 可选；留空由 AI 生成 |

`POST /api/docs/merge` → 后端直接 `repo.write` 到正式路径，正常索引，侧栏立即可见。

### 阶段 2：预览 + 分流（核心）

自动打开新文档预览。DocViewer 底部显示 **合并审阅条**（仅当该文档有关联的 pending 合并会话时）：

```
正在审阅合并结果（源自 4 篇文档）
[删除此文]  [重新生成]  [采用]
```

| 操作 | 行为 |
|------|------|
| **采用** | 标记合并会话 `accepted`；收起审阅条；进入阶段 3（征询删原文）；**无论是否改过正文均不弹确认** |
| **重新生成** | 见下方「智能确认」；通过后同源同路径覆盖；刷新预览；更新 `generated_content_hash` |
| **删除此文** | 见下方「智能确认」；通过后删新文档；会话 `rejected`；关闭预览；源文档不动 |

#### 智能确认（重新生成 / 删除此文）

判断「用户是否改过正文」：`当前文件正文 hash ≠ merge_session.generated_content_hash`。

| 用户是否改过 | 重新生成 | 删除此文 |
|--------------|----------|----------|
| **未改** | 直接覆盖重生 | 直接删除 |
| **已改** | 弹窗：「文档已修改，重新生成将覆盖你的编辑，是否继续？」 | 弹窗：「文档已修改，删除将丢失你的编辑，是否继续？」 |

- 检测以后端 hash 为准（含用户在 IDE 里改文件的情况）。
- 前端若在 DocViewer 内编辑，保存成功后同步更新本地 `userModified` 标记，**点击时先读本地标记**：已为 true 则立即弹窗，无需等 API；否则可再请求 `GET /api/docs/merge/{id}` 的 `user_modified` 兜底。
- 每次合并或重新生成写入成功后，刷新 `generated_content_hash` 并将本地 `userModified` 置 false。

用户关闭预览未点任何按钮 → 新文档**保留在知识库**；下次打开该文档时审阅条仍出现，直到采用或删除。

用户可在审阅期间编辑并保存文档正文；保存后视为「已改」，后续重生/删除走确认流程。

### 阶段 3：征询删除源文档

点「采用」后展示 `PendingQuestion`（`multi_select: true`）：

> 已保留合并文档《{path}》。是否删除以下源文档？

源文档列表 checkbox，**默认全不勾选**：

- **删除所选**
- **全部保留**

删除走 `delete_kb`；禁止删 `系统/` 等受保护路径。

## 后端设计

### 合并会话（非草稿）

`.kb/merge_sessions.json` 仅存元数据，不存正文：

```json
{
  "id": "uuid",
  "status": "pending_review | accepted | rejected",
  "new_path": "技术/AI内容创作/漫剧行业合并.md",
  "source_paths": ["...", "..."],
  "instruction": "",
  "order": ["...", "..."],
  "generated_content_hash": "sha256:...",
  "created_at": "...",
  "updated_at": "..."
}
```

`generated_content_hash`：最近一次合并/重新生成写入后，对**正文**（不含 frontmatter 或统一规范化后）计算的 SHA-256。用于 `user_modified` 判断。

- `pending_review`：预览时显示审阅条。
- `accepted`：已采用；若源文档征询未完成，仍可通过 `/api/questions` 处理。
- `rejected`：用户删掉了新文档；会话归档，不再展示审阅条。

### `Organizer.merge_documents`

```python
def merge_documents(
    self,
    source_paths: list[str],
    *,
    instruction: str = "",
    order: list[str] | None = None,
    target_path: str | None = None,  # regenerate 时传入，覆盖同路径
) -> MergeResult:
```

1. 校验：`len(source_paths) >= 2`；路径存在；不可含 `系统/`。
2. 读取源文档全文（按 `order`）。
3. `_synthesize_merge` — LLM 全局重构。
4. `_decide` 得 `rel_path` / `title`（`action=new`）；regenerate 时用已有 `target_path`。
5. `repo.write` + `indexer.index_file` — **正式文档**。
6. frontmatter 写入追溯字段（非草稿语义）：

   ```yaml
   merged_from:
     - 技术/AI内容创作/文档A.md
     - 技术/AI内容创作/文档B.md
   ```

7. 新建或更新 `merge_sessions` 记录，`status=pending_review`，写入 `generated_content_hash`。
8. 返回 `MergeResult(merge_id, rel_path, source_paths, user_modified: false)`。

### API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/docs/merge` | 首次合并：`{ paths, instruction?, order?, title? }` |
| POST | `/api/docs/merge/{id}/regenerate` | 同源、同路径覆盖重生 |
| POST | `/api/docs/merge/{id}/accept` | 采用 → 创建删原文征询 |
| POST | `/api/docs/merge/{id}/reject` | 删除新文档 + 会话 rejected |
| GET | `/api/docs/merge/{id}` | 会话元数据 + `user_modified: bool`（供恢复审阅条与确认判断） |
| GET | `/api/docs/merge/active?path=` | 按文档路径查 pending 会话 |
| POST | `/api/docs/merge/{id}/resolve-sources` | `{ delete_paths: string[] }` 删除所选源文档 |

无 `confirm`、`discard`、`drafts` 相关端点。

### 重新生成 vs 删除

- **重新生成**：`merge_documents(..., target_path=session.new_path)`，git commit message 如 `merge: regenerate 覆盖 {path}`。
- **删除此文**：`repo.delete(session.new_path)` + `indexer.remove` + `status=rejected`。若用户之后又点合并，走全新 `POST /api/docs/merge`。

## 前端改动范围

| 文件 | 改动 |
|------|------|
| `FileTree.tsx` | 多选模式 |
| `Sidebar.tsx` | 多选开关、浮条、合并配置 |
| `App.tsx` | `selectionMode`、`selectedPaths`、`mergeReview` 会话状态 |
| `DocViewer.tsx` | 合并审阅条：采用 / 重新生成 / 删除此文 |
| `api.ts` | merge API |
| `PendingQuestion.tsx` | 复用（删源文档） |
| `index.css` | 多选、浮条、审阅条样式 |

## 状态模型（App 层）

| 状态 | 类型 | 说明 |
|------|------|------|
| `selectionMode` | `boolean` | 多选模式 |
| `selectedPaths` | `Set<string>` | 已选路径 |
| `mergeReview` | `{ mergeId, newPath, sourcePaths, userModified } \| null` | 待审阅合并；`userModified` 本地编辑或 API 同步 |

页面加载时：若 `previewPath` 有关联 pending 会话（`GET /api/docs/merge/active?path=`），恢复审阅条。

## 错误处理

| 场景 | 处理 |
|------|------|
| 少选（<2） | 「合并」disabled |
| 源文件缺失 | 合并前校验报错 |
| LLM 失败 | 不写文件、不建会话 |
| 重新生成失败 | 保留旧版正文，提示错误 |
| 删除新文档时会话已 accepted | 不允许删（或需二次确认「已采用，确定删除？」） |
| 删源文档时部分不存在 | 跳过并汇总 |

## 验收

1. 多选 4 篇 → 合并 → 侧栏立即出现新文档，右侧预览，结构为全局重构非拼接。
2. **未改正文**时点「重新生成」→ 无弹窗，直接覆盖；点「删除此文」→ 无弹窗，直接删除。
3. **改过正文**后点「重新生成」→ 弹覆盖确认；确认后才覆盖。
4. **改过正文**后点「删除此文」→ 弹删除确认；确认后才删除。
5. **采用** → 无论是否改过，均不弹确认；审阅条消失；征询删源。
6. 未点采用就关掉预览 → 新文档仍在树中；再次打开仍见审阅条。
7. `系统/` 文档不可参与合并。

## 与 v1（草稿方案）差异

| v1 草稿方案 | v2 当前方案 |
|-------------|-------------|
| `.kb/drafts/` 暂存 | 直接写正式路径 |
| 确认入库 | 采用 / 删除 / 重新生成 |
| 放弃草稿 | 删除此文 |
| 两阶段落库 | 一次写入 + 事后取舍 |
