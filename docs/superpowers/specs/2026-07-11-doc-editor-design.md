# 文档编辑：Preview / Markdown 双模式

日期：2026-07-11  
状态：已实现

## 问题

`DocViewer` 当前只读（`GET /api/doc` + `MarkdownContent` 渲染）。用户无法在应用内修改知识库文档，只能到磁盘改文件或依赖对话 Agent 合并写入。需要像 IDE 一样：**既能看渲染效果边写，也能切回纯 Markdown 源码编辑**。

## 核心原则

1. **单一数据源**：编辑中的正文始终是 `body: string`（不含 frontmatter）。
2. **单一渲染管线**：预览、阅读、保存后展示均使用现有 `react-markdown` + `remark-gfm`（`MarkdownContent`）。**不为** `---`、标题、列表等语法单独写转换逻辑；渲染结果完全由 remark 决定。
3. **Preview 可输入**：用户在 Preview 模式敲下的字符写入 `body`，界面立即用 `MarkdownContent` 重绘。例如连续输入 `-`、`-` 显示两个连字符，再输入第三个 `-` 且满足 GFM 规则时，remark 自动渲染为分割线。

## 目标

1. 打开文档后默认 **Preview** 模式：显示渲染结果，**可直接输入**修改 `body`。
2. 标题栏提供 **Preview ⇄ Markdown** 切换；Markdown 模式编辑源码（`body` 明文）。
3. **手动保存**（按钮 + `Ctrl+S` / `Cmd+S`）；未保存切换文档或关闭时提示。
4. 保存后：`write_doc` + `reindex_doc`（向量与全文索引同步更新），刷新侧栏树。
5. Frontmatter（`title`、`tags` 等）首版**只读展示**，不进入编辑区；保存时原样写回。

## 非目标

- 不引入第二套 WYSIWYG / HTML 渲染引擎。
- 不为各 Markdown 语法实现手写 input rules（全靠 remark）。
- 首版不做 frontmatter 表单编辑、版本对比、协同编辑。
- 不做自动保存 / 防抖保存（避免频繁 git commit 与嵌入 API 调用）。
- Preview 模式首版不追求 Typora 级「光标与渲染像素级对齐」；复杂结构（宽表格、大段代码）鼓励切 Markdown 模式。
- 不修改合并草稿 spec 的流程（后续可复用同一编辑器组件）。

## 模式定义

| 模式 | 显示 | 输入 | 典型场景 |
|------|------|------|----------|
| **Preview** | `MarkdownContent(body)` | 按键修改 `body`，即时重渲染 | 日常写段落、标题、分割线 |
| **Markdown** | `body` 源码（CodeMirror 6 或等效编辑器） | 直接编辑字符串 | 表格、代码块、精确改几个字 |

两种模式共享同一份内存中的 `body` 与 `selection`；切换前将当前编辑器状态 flush 到 `body`，切换后从 `body` 初始化另一视图。

### Preview 输入模型

```
用户按键 / IME 提交
  → 在 body[selectionStart:selectionEnd] 插入或删除字符
  → 更新 selection
  → React 重渲染 MarkdownContent(body)
  → 恢复焦点与 selection（best-effort）
```

示例（单独一行的 `---`）：

| 操作后 body 片段 | 屏幕显示（经 remark） |
|------------------|----------------------|
| `-` | 一个连字符 |
| `--` | 两个连字符 |
| `---`（独占一行） | 水平分割线 |

语法是否变成 HR、标题等，**全部由 remark-gfm 决定**，编辑器不判断。

### Preview 实现要点（首版）

推荐组件 `DocLivePreview`：

- 可聚焦根节点（`tabIndex={0}`），承接键盘与 IME。
- 展示层：`<MarkdownContent>{body}</MarkdownContent>`（`pointer-events: none`，避免误点链接跳转）。
- 输入层（二选一，实现时择一）：
  - **A. 同步 textarea 叠层**：透明文字 + 可见 caret，与 `body` 双向绑定；布局与渲染不完全重合时仍可输入，首版可接受。
  - **B. 键盘事件直写 body**：`beforeinput` / `keydown` 维护 `body` + `{ start, end }` 字符偏移；实现简单，需处理中文 IME `composition` 会话。
- **必须**正确处理 `compositionstart` / `compositionupdate` / `compositionend`，避免中文输入被打断。

## 保存与索引

### 后端 API

```
PUT /api/doc
Content-Type: application/json

{
  "path": "技术/foo.md",
  "body": "…正文…"
}
```

响应：

```json
{
  "rel_path": "技术/foo.md",
  "meta": { … },
  "body": "…"
}
```

逻辑：

1. `repo.read_doc(path)` 取现有 `meta`（不存在则 404）。
2. 禁止写入受保护路径（`.kb/`、`.git/`、`系统/` 等，与 `delete_path` 规则一致）；`系统/` 下文档若允许编辑，至少需二次确认（首版可禁止 PUT）。
3. `repo.write_doc(path, meta, body, commit_msg="edit: {path}")`。
4. `indexer.reindex_doc(path, body)`。
5. 可选：`repo.log_change("用户编辑 {path}")`。

### 前端保存

- `saveDoc(path, body)` → `PUT /api/doc`。
- 成功：`savedBody` 对齐、`dirty=false`，调用 `onSaved(path)` → App 层 `refreshKb(path)`。
- 失败：保留本地 `body`，toast / 内联错误信息。

### 与磁盘直改的关系

本功能不解决「用户在 IDE 改文件后索引过期」；仍依赖下次经 API 写入或未来增量 reindex。在范围内：经本编辑器保存的文档索引始终最新。

## 状态模型（DocViewer 层）

| 状态 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `editMode` | `'preview' \| 'markdown'` | `'preview'` | 当前编辑模式 |
| `body` | `string` | 自 API 加载 | 编辑中正文 |
| `savedBody` | `string` | 自 API 加载 | 上次保存快照 |
| `dirty` | `boolean` | `false` | `body !== savedBody` |
| `selection` | `{ start, end }` | — | 字符偏移，模式切换与保存后恢复用 |
| `saving` | `boolean` | `false` | 保存中禁用重复提交 |
| `readOnly` | `boolean` | 按路径 | 受保护文档为 true |

打开新 `path` 或 `refreshKey` 变化时：

- 若 `dirty`，先 `confirm` 放弃或保存。
- 重新 `getDoc`，重置 `body` / `savedBody` / `dirty` / `editMode`（`editMode` 可保留用户上次偏好，存在 `sessionStorage`）。

## 交互

1. 打开文档 → 进入 Preview，可立即输入。
2. 标题栏右侧：`[Preview | Markdown]` 分段切换；`dirty` 时标签旁显示圆点。
3. **保存**：标题栏按钮；快捷键 `Ctrl+S` / `Cmd+S`（两种模式均生效）。
4. **关闭文档 / 切换预览文件**：`dirty` 时确认。
5. **Esc**：不保存（与阅读区 spec 区分：编辑中 `Esc` 不关闭文档，避免误触；或首版 Esc 仅退出专注，关闭仍用 ×）。
6. 元数据区（`doc-meta`）只读；`conversation_id` 链接等行为不变。
7. 阅读布局（窄/宽/专注/浮窗）与现有 `DocViewer` props 兼容；编辑不强制进入专注，但专注下编辑长文体验更好。

## 实现范围

| 位置 | 改动 |
|------|------|
| `backend/app/api/routes.py` | `PUT /api/doc`；`UpdateDocBody` 模型 |
| `backend/app/storage/repo.py` | 可选：`is_writable(rel_path)` 复用保护路径逻辑 |
| `backend/tests/test_api.py` | 保存、404、受保护路径、reindex 冒烟 |
| `frontend/src/api.ts` | `saveDoc(path, body)` |
| `frontend/src/components/DocViewer.tsx` | 编辑态、模式切换、保存、dirty 提示 |
| `frontend/src/components/DocLivePreview.tsx` | **新建** Preview 输入 + 渲染 |
| `frontend/src/components/DocMarkdownSource.tsx` | **新建** 源码编辑器（首版可用 `textarea`，推荐 CodeMirror 6） |
| `frontend/src/App.tsx` | `onDocSaved` → `refreshKb` |
| `frontend/src/index.css` | 模式切换、dirty 指示、编辑区焦点样式 |

依赖：首版 Markdown 模式可用原生 `textarea`；若引入 CodeMirror 6，仅作用于 Markdown 模式，Preview 仍只用 `MarkdownContent`。

## 错误处理

| 场景 | 处理 |
|------|------|
| 文档不存在 | 加载 404，关闭编辑 |
| 保存时文档已被删 | 404 提示，保留本地 `body` 供复制 |
| 受保护路径 | 403 / 只读，隐藏保存 |
| 嵌入 API 失败 | 与现有一致：`reindex_doc` 内向量失败仍更新 FTS，保存成功 |
| 网络失败 | 保留 `dirty`，可重试保存 |

## 验收

1. Preview 模式：输入 `---`（独占一行）→ 显示分割线；切 Markdown 可见源码为 `---`。
2. Markdown 模式：改标题为 `## Foo` → 切 Preview 显示二级标题。
3. 两种模式切换不丢字、`dirty` 状态正确。
4. 保存后刷新页面内容一致；`search_kb` / 问答能检索到新内容（reindex 生效）。
5. 未保存关闭文档有确认；保存后 `dirty` 清除，侧栏树 `updated` 可见（若展示 mtime）。
6. 中文 IME 输入一句完整话无乱码、无中途截断。
7. `系统/` 下文档按只读或禁止保存策略生效。

## 后续可选

- 合并草稿（`2026-07-11-multi-doc-merge-design.md`）复用 `DocLivePreview` / `DocMarkdownSource`。
- frontmatter 轻量表单（title、tags）。
- 保存说明作为 git commit message 后缀。
- 外部文件变更检测与手动「重建索引」。
