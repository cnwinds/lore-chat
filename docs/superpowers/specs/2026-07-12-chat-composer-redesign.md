# 聊天输入区重设计：Composer 卡片 + 文档托盘 + 模型化合并

日期：2026-07-12  
状态：已评审，待实现  
效果图：`assets/chat-composer-tray-v2.png`（项目内 mockup）  
前置文档：[2026-07-12-web-search-toggle-design.md](./2026-07-12-web-search-toggle-design.md)、[2026-07-12-partial-doc-edit-design.md](./2026-07-12-partial-doc-edit-design.md)、[2026-07-11-multi-doc-merge-design.md](./2026-07-11-multi-doc-merge-design.md)、[2026-07-11-doc-reader-layout-design.md](./2026-07-11-doc-reader-layout-design.md)

## 0. 复审摘要

用户评审通过的设计要点：

| 项 | 决策 |
|----|------|
| 输入区形态 | 扁平 `chat-input-bar` → **三层 Composer 卡片** |
| 文档托盘 | 无「当前文档」标题、无「+ 添加」按钮；仅一排 chip |
| 主文档标识 | chip **左侧靛蓝竖条**（非星标、非「正在编辑」文案） |
| 主文档与右侧栏 | **联动**：主文档 chip 对应右侧 `DocViewer` 预览内容 |
| 目录树选文 | **单击** → 托盘替换为单篇并设为主文档；**Ctrl+单击** → 追加到托盘 |
| 托盘操作 | 点击 chip → 设为主文档；chip 上 **×** → 从托盘移除 |
| 联网开关 | 工具行左侧**纯图标**按钮；开/关仅通过**色彩**区分，无文字 |
| 文件上传 | 选文件 → **先显示 chip、随消息发送**，非静默归档 |
| 合并能力 | **撤专用合并 UI**，改由「托盘多选 + 对话」驱动；删源由模型 `ask_user` 询问 |
| 删源确认 | 模型问「是否删除源文档」，用户选保留或删除（默认保留） |

## 1. 问题

### 1.1 输入区

当前 `Chat.tsx` 的 `chat-input-bar` 将输入框、附件、联网、发送、沉淀挤在同一行：

- **联网按钮**使用 GitHub 绿 `#1f883d`，与产品靛蓝主题 `--accent` 冲突，视觉权重与发送键同级，显得突兀。
- **文件上传**选文件后立即 `uploadFile` 并追加 assistant 消息「已保存文件：…」，输入框内无任何展示，用户感知为「没反应」。
- **当前文档**仅以 `previewPath` 隐式传给后端 `active_doc_path`，输入区无可见绑定，用户不知道 Agent 默认会改哪篇。

### 1.2 多文档与合并

现有 [多文档合并 spec](./2026-07-11-multi-doc-merge-design.md) 通过侧栏「多选模式」+ 配置弹窗 + 审阅条完成功能化流程。用户希望：

- 在目录树中 **Ctrl+单击** 多选文档作为操作对象；
- 用自然语言（如「合并成一篇手册」）驱动，**取代专用合并功能**；
- 工作流全部 **模型化**，减少独立功能入口。

同时需避免「多篇当前文档」导致写入目标歧义。

## 2. 目标

1. 重设计聊天输入区为 **Composer 卡片**，图形化展示：文档托盘、待发送附件、联网状态。
2. 建立 **文档托盘** 为唯一真相源：读上下文（多篇）+ 写目标（唯一主文档）语义分离。
3. 目录树单击/Ctrl+单击与托盘、右侧栏三方联动。
4. 文件上传改为 **附加到 Composer → 随消息发送**。
5. 合并场景退化为对话能力，保留 **草稿审阅 + 删源确认** 安全网，下线专用合并 UI。

## 3. 非目标

- 不做托盘内拖拽排序（合并顺序由用户在对话中说明，或 Phase 2 再加）。
- 不做三栏布局重构（沿用现有侧栏 + 主区 + 右侧 `DocViewer`）。
- 本次不改动 `/ingest`、`/ask` 端点。
- 不删除后端 `Organizer.merge_documents` 等能力（可作为 Agent 工具内部实现）；仅下线前端专用入口与审阅条 UI。

## 4. 方案总览

```
┌─ Composer 卡片 ─────────────────────────────────────────────┐
│  [托盘]  │Docker 常用命令│ │容器网络配置│ │镜像构建笔记│      │
│          ↑主文档(左竖条)   ↑参考(灰竖条)                     │
│  [输入]  把这 3 篇合并成一篇 Docker 运维手册…                │
│  [工具]  📎  🌐                         沉淀    ➤ 发送        │
│          附件 联网(图标，色彩表开/关)                          │
└─────────────────────────────────────────────────────────────┘
         │ 主文档                           │
         └──────────────────────────────────┘
                    右侧 DocViewer 同步展示
```

## 5. Composer 卡片结构

### 5.1 三层分区

| 层 | 类名建议 | 出现条件 | 内容 |
|----|----------|----------|------|
| 托盘行 | `composer-tray` | `tray.length > 0` 或 `pendingFiles.length > 0` | 文档 chip + 文件 chip |
| 输入行 | `composer-input` | 始终 | `textarea` |
| 工具行 | `composer-toolbar` | 始终 | 左：附件、联网；右：沉淀、发送 |

托盘与输入行之间用 `--border` 细分隔线；卡片整体 `border-radius: var(--radius-lg)`、`box-shadow: var(--shadow-sm)`。

### 5.2 联网开关样式

取代现有 `chat-web-btn`（绿色文字胶囊 `🌐 联网`）：

**形态**：与附件按钮同级的**独立图标按钮**，仅渲染地球 SVG/图标，**不显示任何文字**（无「联网」标签、无激活圆点、无药丸背景文案）。

| 状态 | 色彩表达 |
|------|----------|
| **关** | 图标 `--text-muted`；背景透明；边框无或 `--border` 细描边；与附件按钮视觉权重一致 |
| **开** | 图标 `--accent`；背景 `--accent-soft`；边框 `--accent-border`（可选圆角方块，与附件按钮同尺寸） |

- 开/关**仅通过上述色彩变化**传达，不依赖文字或额外标记。
- 可访问性：`aria-pressed`、`aria-label` / `title` 保留（「联网搜索：开」「联网搜索：关」），悬停时 tooltip 说明语义。
- 行为与 [web-search-toggle spec](./2026-07-12-web-search-toggle-design.md) 一致：`localStorage` 记忆，`web_enabled` 透传 `/chat`。

### 5.3 文件附件 chip

| 阶段 | 行为 |
|------|------|
| 选择文件 | 在托盘行追加 chip：类型图标 + 文件名 + 大小 + × |
| 发送前 | 仅本地状态，不上传 |
| 发送时 | 先 `uploadFile`（或批量），将 `attachments[]` 写入用户消息；再 `chatStream` |
| 用户消息气泡 | 回放附件 chip（可点击下载） |

移除「选文件即静默归档并只追加 assistant 消息」的现有逻辑。

## 6. 文档托盘

### 6.1 状态模型

```typescript
type DocTrayItem = {
  path: string;       // 知识库相对路径
  title: string;      // 展示名（文件名或 meta.title）
};

type ComposerDocState = {
  items: DocTrayItem[];   // 顺序即 Agent 阅读顺序提示
  primaryPath: string | null;  // 必须 ∈ items；items 非空时不得为 null
};
```

**唯一真相源**：`App` 层持有 `ComposerDocState`，`Chat`、`Sidebar`、`DocViewer` 均读写此状态。

### 6.2 读 / 写语义

| 角色 | 范围 | 传给 Agent |
|------|------|------------|
| **读·上下文** | 托盘内全部 `items` | `active_doc_paths: string[]`（新字段） |
| **写·默认目标** | 唯一 `primaryPath` | `primary_doc_path: string`（替代现有单字段 `active_doc_path`） |

Prompt 约定（`prompts.py`）：

- 用户说「改一下」「补充一段」且未指定路径 → `edit_doc` / `write_kb+target_path` 默认落 `primary_doc_path`。
- 托盘内其余文档仅作参考，不得擅自修改，除非用户点名或合并类「多进一出」操作。

### 6.3 Chip 视觉

- **主文档**：左侧 **3px 靛蓝竖条** `--accent`，浅靛蓝底 `--accent-soft`，文件名 `--text-primary`。
- **参考文档**：左侧 1px 灰竖条 `--border-strong`，白/灰底，文件名 `--text-secondary`。
- **公共**：文档图标 + 截断标题 + 右侧 ×（hover 显示）。
- **无**「当前文档」标签、**无**「+ 添加」按钮。

点击 chip 正文区域 → `setPrimary(path)`；点击 × → `removeFromTray(path)`。

### 6.4 移除与主文档切换规则

| 操作 | 规则 |
|------|------|
| 移除主文档 | 若托盘仍有其他项，**自动**将下一项（按当前顺序）设为主文档；若托盘为空，`primaryPath = null`，关闭右侧栏 |
| 移除参考文档 | 仅删该项 |
| 托盘变空 | 隐藏托盘行；`primary_doc_path` 不传 |

### 6.5 软上限

托盘文档数建议软上限 **8 篇**；超出时 toast 提示「已选较多，模型将优先读取大纲」，Agent 侧对超长列表只注入路径 + 按需 `read_doc`（实现时 orchestrator 可截断注入，不全文塞入 system prompt）。

## 7. 目录树交互

取代现有「多选模式」开关（`selectionMode`）作为**添加文档到托盘**的主要入口。

| 操作 | 行为 |
|------|------|
| **单击**文件 | `tray = [该文档]`，`primary = 该文档`，打开右侧 `DocViewer` |
| **Ctrl+单击**（Mac：`⌘+单击`） | 若已在托盘 → 无操作或 toggle 移除（实现取「无操作」更简单）；若不在 → `tray.push`，不设主文档（保持原 primary） |
| **双击** | 与单击相同（不单独定义） |
| **Shift+单击** | 保留现有文件夹内范围多选，行为等同多次 Ctrl+单击追加 |

侧栏底部可保留一行极淡提示（仅首次或 hover 帮助）：`单击替换 · Ctrl+单击添加`；Composer 内不展示。

### 7.1 与右侧栏联动

- `primaryPath` 非空 → `DocViewer` 展示该路径（`docPinned` 策略沿用现有：用户可浮窗/固定）。
- 用户在托盘点击其他 chip 设为主文档 → 右侧栏切换文档。
- 用户关闭右侧栏 ≠ 清空托盘（托盘仍保留上下文）；若需「关闭即清空」可作为 Phase 2 选项，**本次不做**。

## 8. 合并：从功能化到模型化

### 8.1 用户流程（新）

```
目录树 Ctrl+单击选 N 篇 → 托盘显示 N 个 chip → 设主文档（可选，合并可不设主）
    → 输入「合并成一篇 XXX」→ 发送
    → Agent：read_doc × N → write_kb 生成新文档
    → 右侧自动打开新文档预览（用户审阅、可手工改）
    → Agent：ask_user「是否删除以下源文档？」选项：保留 / 删除（可多选源文档）
    → 用户确认后 delete_kb（若选删除）
```

### 8.2 保留的安全网

从 [multi-doc-merge spec](./2026-07-11-multi-doc-merge-design.md) **保留**的能力，改由 Agent + 通用 UI 承载：

| 原合并功能 | 新承载 |
|------------|--------|
| 生成结果为可审阅新文档 | `write_kb` + 右侧 `DocViewer` 打开 |
| 用户手工修改 | `DocViewer` 现有编辑/保存/diff |
| 不满意重新生成 | 用户对话「重新生成合并稿」；Agent 覆盖同路径 `write_kb` |
| 不满意删除 | 用户对话「删除这篇合并稿」或 DocViewer 关闭+删除 |
| 删源确认 | **`ask_user`**，默认「保留源文档」 |
| `generated_content_hash` / 改过确认 | Phase 2：可在 `write_kb` 结果 meta 记 `source_paths`；重生前 Agent `read_doc` 对比。Phase 1 靠用户对话显式确认 |

### 8.3 下线项

| 下线 | 说明 |
|------|------|
| 侧栏「多选」模式开关 | 由 Ctrl+单击替代 |
| `MergeConfigModal` | 合并说明/标题改在对话中表达 |
| 侧栏底部「已选 N 篇 · 合并为文档」浮条 | 移除 |
| `DocViewer` 底部 **合并审阅条** | 移除；审阅靠对话 + 右侧编辑 |
| `MergeSourceQuestion` 独立组件 | 合并入通用 `PendingQuestion` / `ask_user` 渲染 |

后端 `POST /api/docs/merge`、`merge_sessions.json`：**Phase 1 保留 API 不删**（避免破坏测试/脚本）；前端不再调用。Phase 2 评估是否将合并逻辑收敛为 Agent 工具内部函数。

### 8.4 Prompt 补充（《戒律》/ SYSTEM_PROMPT）

```markdown
## 文档合并
1. 用户托盘内多篇文档且要求合并时：通读全文、按主题去重重组，禁止流水线拼接；结果写入**新文档**。
2. 合并完成后必须 ask_user 询问是否删除源文档；默认保留，用户明确选择才可 delete_kb。
3. 不得在未询问的情况下删除源文档。
```

## 9. 后端 API 变更

### 9.1 `POST /api/chat` 请求体

```python
class ChatBody(BaseModel):
    text: str
    conversation_id: str | None = None
    active_doc_paths: list[str] = []      # 新增：托盘全部路径
    primary_doc_path: str | None = None   # 新增：主文档；须在 active_doc_paths 内
    web_enabled: bool = False
    attachments: list[str] = []           # 新增：已上传附件相对路径
```

- **兼容**：保留 `active_doc_path` 单字段一个版本周期，若存在则等价于 `active_doc_paths=[path]` + `primary_doc_path=path`。
- Orchestrator `run()` 注入 system suffix：列出 `active_doc_paths`；强调 `primary_doc_path` 为默认编辑目标。

### 9.2 用户消息持久化

`ChatMessage` 扩展：

```typescript
type ChatMessage = {
  // ...existing
  attachments?: string[];
  doc_context?: string[];   // 发送时托盘路径快照
  primary_doc?: string;
};
```

## 10. 组件与文件

| 文件 | 变更 |
|------|------|
| `frontend/src/components/Chat.tsx` | Composer 三层结构；托盘/附件状态；发送逻辑 |
| `frontend/src/components/ComposerTray.tsx` | **新建**：文档 chip + 文件 chip |
| `frontend/src/components/ComposerToolbar.tsx` | **新建**：附件、联网、沉淀、发送 |
| `frontend/src/App.tsx` | `ComposerDocState`；目录树单击/Ctrl+单击；与 `previewPath` 统一 |
| `frontend/src/components/FileTree.tsx` | 传 `ctrlKey`/`metaKey`；移除多选模式 UI |
| `frontend/src/components/Sidebar.tsx` | 移除多选开关与合并浮条 |
| `frontend/src/index.css` | Composer、chip、联网开关新样式；删除绿色 `chat-web-btn--on` |
| `backend/app/api/routes.py` | `ChatBody` 扩展 |
| `backend/app/engine/agent/orchestrator.py` | 多文档 context 注入 |
| `backend/app/engine/agent/prompts.py` | 托盘语义 + 合并删源规则 |

## 11. 测试计划

### 11.1 前端

- 单击文件：托盘仅 1 篇且为主文档，右侧栏打开。
- Ctrl+单击：托盘追加，主文档不变。
- 点击 chip：切换主文档，右侧栏切换。
- 点击 ×：移除；移除主文档时下一篇升主。
- 选文件：托盘出现文件 chip；发送后用户消息含附件。
- 联网开关：开/关样式、localStorage、请求体 `web_enabled`。

### 11.2 后端

- `primary_doc_path` 不在 `active_doc_paths` 内 → 400。
- Agent 收到多路径 context；`edit_doc` 默认 path 为 `primary_doc_path`。
- 合并对话后 `ask_user` 出现；未确认不调用 `delete_kb`。

### 11.3 回归

- 无托盘时聊天正常。
- `edit_doc` / `read_doc` / 沉淀会话无回归。
- 旧会话历史无 `doc_context` 字段时正常渲染。

## 12. 实现阶段

### Phase 1（本次）

- Composer 卡片 + 托盘 + 联网样式 + 附件随发送
- 目录树单击 / Ctrl+单击
- 主文档 ↔ 右侧栏联动
- `ChatBody` 多文档字段 + Prompt
- 下线前端合并专用 UI
- 合并删源走 `ask_user`

### Phase 2（可选）

- 托盘拖拽排序
- 合并「改过确认」与 `source_paths` meta
- 下线 `POST /api/docs/merge` API
- `PUT /api/doc` 与托盘主文档脏状态冲突提示

## 13. 决策记录

| 项 | 决策 |
|----|------|
| 托盘标签文案 | **不显示**「当前文档」 |
| 添加文档入口 | **仅目录树** Ctrl+单击，无「+ 添加」 |
| 主文档标识 | chip **左侧靛蓝竖条** |
| 主文档与右侧栏 | **强制联动** |
| 写入歧义 | 唯一 `primaryPath`；合并为「多进一出」新建 |
| 删源 | 模型 **`ask_user`**，默认保留 |
| 合并 UI | **下线**专用流程，保留安全语义 |
| 联网开关形态 | **纯图标**，无文字；开/关靠色彩（灰 ↔ 靛蓝） |
| 联网配色 | **靛蓝主题**，弃用 `#1f883d` 与文字胶囊 |
