# 聊天 Composer 重设计实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现。步骤用 `- [ ]` 跟踪。后端步骤遵循 TDD；前端以 `npm run build` + 手验清单为主（尚无 Vitest）。

**Goal:** 将聊天输入区升级为三层 Composer 卡片（文档托盘 + 输入 + 工具行），支持多文档上下文与唯一主文档、纯图标联网开关、附件随发送；目录树单击/Ctrl+单击驱动托盘；下线专用合并 UI，合并改由对话 + `ask_user` 删源确认。

**Spec:** [2026-07-12-chat-composer-redesign.md](../specs/2026-07-12-chat-composer-redesign.md)

**Tech Stack:** Python 3.11 / FastAPI / pytest；React 19 + TypeScript + Vite。

**Architecture:** 后端先行（`ChatBody` 多文档字段 + orchestrator 注入 + Prompt）；前端 `App` 持有 `ComposerDocState` 唯一真相源，新建 `ComposerTray` / `ComposerToolbar`，`Chat` 消费状态；`previewPath` 由 `primaryPath` 驱动。与 [frontend-god-component-split](./2026-07-12-frontend-god-component-split.md) **分开 PR**：本计划改用户可见行为，先做；拆分可在本计划合并后再做。

---

## 决策记录（实现前已定）

| 项 | 决策 |
|----|------|
| 托盘真相源 | `App` → `useComposerDocState` |
| 主文档 ↔ 右侧栏 | `primaryPath` 驱动 `openDocPreview(path, undefined, { pin: true })` |
| 目录树 | 单击替换托盘；Ctrl/⌘+单击追加 |
| 联网开关 | 纯图标，色彩表开/关 |
| 附件 | 选文件 → chip → 发送时 upload |
| 合并 UI | 下线侧栏多选/浮条/审阅条/`MergeConfigModal`/`MergeSourceQuestion` |
| 后端 merge API | Phase 1 保留，前端不调 |

---

## 目标文件结构

```
frontend/src/
  types/composer.ts              # DocTrayItem, ComposerDocState, PendingFile
  hooks/useComposerDocState.ts   # 托盘增删改、主文档切换
  components/
    ComposerTray.tsx             # 文档 chip + 文件 chip
    ComposerToolbar.tsx          # 附件、联网图标、沉淀、发送
    Chat.tsx                     # 改用 Composer，删旧 input-bar
  App.tsx                        # 托盘状态 + 目录树交互
  api.ts                         # chatStream 多文档 + attachments

backend/app/
  api/routes.py                  # ChatBody 扩展 + 校验
  engine/agent/orchestrator.py   # active_doc_paths / primary_doc_path
  engine/agent/prompts.py        # 托盘语义 + 合并删源
  engine/agent/system_layer.py   # 《戒律》§文档合并（可选追加）
```

---

# 后端流

## Task B1: `ChatBody` 多文档 + 附件字段

**Files:**
- Modify: `backend/app/api/routes.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: 写失败测试**

`test_api.py` 追加：

```python
def test_chat_rejects_primary_not_in_active_paths(client):
    r = client.post(
        "/api/chat",
        json={
            "text": "hi",
            "active_doc_paths": ["a.md"],
            "primary_doc_path": "b.md",
        },
    )
    assert r.status_code == 400


def test_chat_accepts_multi_doc_context(client):
    r = client.post(
        "/api/chat",
        json={
            "text": "合并",
            "active_doc_paths": ["a.md", "b.md"],
            "primary_doc_path": "a.md",
            "web_enabled": False,
        },
    )
    assert r.status_code == 200
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_api.py -k "primary_not_in_active or multi_doc_context" -q
```

Expected: FAIL

- [ ] **Step 3: 扩展 `ChatBody` 与校验**

`routes.py`：

```python
class ChatBody(BaseModel):
    text: str
    conversation_id: str | None = None
    active_doc_path: str | None = None  # 兼容旧字段
    active_doc_paths: list[str] = []
    primary_doc_path: str | None = None
    web_enabled: bool = False
    attachments: list[str] = []


def _normalize_chat_docs(body: ChatBody) -> tuple[list[str], str | None]:
    paths = list(body.active_doc_paths)
    primary = body.primary_doc_path
    if body.active_doc_path:
        if not paths:
            paths = [body.active_doc_path]
        if primary is None:
            primary = body.active_doc_path
    if primary is not None and primary not in paths:
        raise HTTPException(400, "primary_doc_path 必须在 active_doc_paths 内")
    return paths, primary
```

`/chat` handler 内调用 `_normalize_chat_docs(body)`，将 `paths, primary` 传给 `agent.run(...)`。

- [ ] **Step 4: 跑通过**

```bash
cd backend && python -m pytest tests/test_api.py -q
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes.py backend/tests/test_api.py
git commit -m "feat: ChatBody accepts active_doc_paths, primary_doc_path, attachments"
```

---

## Task B2: Orchestrator 多文档上下文注入

**Files:**
- Modify: `backend/app/engine/agent/orchestrator.py`
- Test: `backend/tests/test_agent_orchestrator.py`

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_run_injects_multi_doc_context(orchestrator_factory):
    orch, fake_llm = orchestrator_factory()
    async for _ in orch.run(
        "合并",
        active_doc_paths=["a.md", "b.md"],
        primary_doc_path="a.md",
    ):
        pass
    system_msgs = [m for m in fake_llm.last_messages if m["role"] == "system"]
    joined = "\n".join(m["content"] for m in system_msgs)
    assert "a.md" in joined and "b.md" in joined
    assert "主文档" in joined or "默认编辑" in joined
```

（若 `fake_llm` 无 `last_messages`，在 fake 内记录传入的 `messages`。）

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_agent_orchestrator.py -k multi_doc_context -q
```

- [ ] **Step 3: 扩展 `run()` 签名**

```python
    async def run(
        self,
        user_text: str,
        *,
        mode: str = MODE_DEFAULT,
        active_doc_path: str | None = None,  # 保留兼容
        active_doc_paths: list[str] | None = None,
        primary_doc_path: str | None = None,
        history: list[dict] | None = None,
        conversation_id: str | None = None,
        web_enabled: bool = False,
    ) -> AsyncIterator[str]:
```

在构建 `messages` 时：

```python
        paths = list(active_doc_paths or [])
        primary = primary_doc_path or active_doc_path
        if active_doc_path and active_doc_path not in paths:
            paths = [active_doc_path] if not paths else paths
        if paths:
            lines = [f"- {p}" + ("（主文档，默认编辑目标）" if p == primary else "（参考上下文）") for p in paths]
            messages.append({
                "role": "system",
                "content": "[上下文] 用户当前文档托盘：\n" + "\n".join(lines),
            })
```

`active_doc_path` 传给 `_execute_tool` 时改为 `primary_doc_path or active_doc_path`（`write_kb` / `edit_doc` 默认路径）。

- [ ] **Step 4: 跑通过 + Commit**

```bash
cd backend && python -m pytest tests/test_agent_orchestrator.py -q
git add backend/app/engine/agent/orchestrator.py backend/tests/test_agent_orchestrator.py
git commit -m "feat: orchestrator injects multi-doc tray context and primary target"
```

---

## Task B3: Prompt + 《戒律》合并删源规则

**Files:**
- Modify: `backend/app/engine/agent/prompts.py`
- Modify: `backend/knowledge/系统/戒律.md`（或 `system_layer.py` 内嵌策略）

- [ ] **Step 1: 更新 SYSTEM_PROMPT §7**

将「当前查看的文档」改为「文档托盘」语义：

```python
7. **文档托盘**：用户消息前可能有 system 注入的托盘列表，标注主文档与参考文档。
   - 改字/改段/删段且未指定路径 → edit_doc（path=主文档）
   - 托盘多篇且用户要求合并 → 通读各篇、去重重组，write_kb 写入**新文档**；完成后必须 ask_user 是否删除源文档，默认保留
   - 不得在未 ask_user 确认的情况下 delete_kb 删除托盘内源文档
```

- [ ] **Step 2: 《戒律》追加 §文档合并（两条策略）**

```markdown
## 八、文档合并
1. 用户托盘内多篇文档且要求合并时，结果写入新文档，禁止流水线拼接。
2. 合并后必须询问用户是否删除源文档；默认保留。
```

- [ ] **Step 3: 跑相关测试 + Commit**

```bash
cd backend && python -m pytest -q
git add backend/app/engine/agent/prompts.py backend/knowledge/系统/戒律.md
git commit -m "feat: prompt and 戒律 for tray context and merge delete confirmation"
```

---

# 前端流

## Task F1: 类型与 `useComposerDocState`

**Files:**
- Create: `frontend/src/types/composer.ts`
- Create: `frontend/src/hooks/useComposerDocState.ts`

- [ ] **Step 1: 定义类型**

`composer.ts`：

```typescript
export type DocTrayItem = { path: string; title: string };

export type ComposerDocState = {
  items: DocTrayItem[];
  primaryPath: string | null;
};

export type PendingFile = {
  id: string;
  file: File;
  name: string;
  size: number;
};
```

- [ ] **Step 2: 实现 hook**

`useComposerDocState.ts` 核心 API：

```typescript
export function useComposerDocState() {
  const [items, setItems] = useState<DocTrayItem[]>([]);
  const [primaryPath, setPrimaryPath] = useState<string | null>(null);

  const replaceTray = useCallback((path: string, title: string) => {
    setItems([{ path, title }]);
    setPrimaryPath(path);
  }, []);

  const addToTray = useCallback((path: string, title: string) => {
    setItems((prev) => {
      if (prev.some((i) => i.path === path)) return prev;
      if (prev.length >= 8) {
        window.alert("已选较多，模型将优先读取大纲");
      }
      return [...prev, { path, title }];
    });
  }, []);

  const removeFromTray = useCallback((path: string) => {
    setItems((prev) => {
      const next = prev.filter((i) => i.path !== path);
      return next;
    });
    setPrimaryPath((cur) => {
      if (cur !== path) return cur;
      const remaining = items.filter((i) => i.path !== path);
      return remaining[0]?.path ?? null;
    });
  }, [items]);

  const setPrimary = useCallback((path: string) => {
    setPrimaryPath(path);
  }, []);

  const paths = items.map((i) => i.path);
  return { items, primaryPath, paths, replaceTray, addToTray, removeFromTray, setPrimary };
}
```

（`removeFromTray` 内用 functional update 避免 stale `items`。）

- [ ] **Step 3: Build 校验**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/composer.ts frontend/src/hooks/useComposerDocState.ts
git commit -m "feat: composer doc tray state hook"
```

---

## Task F2: 目录树单击 / Ctrl+单击；移除多选模式

**Files:**
- Modify: `frontend/src/components/FileTree.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: `FileTree` 传修饰键**

`onSelectFile` 签名改为：

```typescript
onSelectFile: (path: string, e?: { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean }) => void;
```

文件行 `onClick`：

```typescript
onClick={(e) => onSelectFile(node.path, { ctrlKey: e.ctrlKey, metaKey: e.metaKey, shiftKey: e.shiftKey })}
```

删除 `selectionMode` 分支及相关 props（`selectedPaths`、`onToggleSelect` 等）。

- [ ] **Step 2: `Sidebar` 移除多选 UI**

删除：多选按钮、`sidebar-selection-bar`、`MergeConfigModal` import 与渲染、`selectionMode` props。

侧栏知识库区底部加淡提示（可选）：

```tsx
<p className="sidebar-tree-hint">单击替换 · Ctrl+单击添加</p>
```

- [ ] **Step 3: `App.tsx` 接线**

```typescript
  const composer = useComposerDocState();

  function handleSelectFile(path: string, mods?: { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean }) {
    const title = path.split("/").pop() ?? path;
    const additive = mods?.ctrlKey || mods?.metaKey;
    if (additive) {
      composer.addToTray(path, title);
    } else {
      composer.replaceTray(path, title);
      openDocPreview(path, undefined, { pin: true });
    }
  }

  function handleTraySetPrimary(path: string) {
    composer.setPrimary(path);
    openDocPreview(path, undefined, { pin: true });
  }

  function handleTrayRemove(path: string) {
    composer.removeFromTray(path);
    if (composer.primaryPath === null && previewPath === path) {
      closeDocPreview();
    }
  }
```

`Chat` props 传入 `composer` 状态与 `onTraySetPrimary` / `onTrayRemove`。

- [ ] **Step 4: Build + Commit**

```bash
cd frontend && npm run build
git add frontend/src/components/FileTree.tsx frontend/src/components/Sidebar.tsx frontend/src/App.tsx
git commit -m "feat: file tree click replaces tray, ctrl+click appends; remove merge selection mode"
```

---

## Task F3: `ComposerTray` 组件

**Files:**
- Create: `frontend/src/components/ComposerTray.tsx`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: 实现 chip 组件**

```tsx
type Props = {
  items: DocTrayItem[];
  primaryPath: string | null;
  pendingFiles: PendingFile[];
  onSetPrimary: (path: string) => void;
  onRemoveDoc: (path: string) => void;
  onRemoveFile: (id: string) => void;
};

export function ComposerTray({ items, primaryPath, pendingFiles, onSetPrimary, onRemoveDoc, onRemoveFile }: Props) {
  if (items.length === 0 && pendingFiles.length === 0) return null;
  return (
    <div className="composer-tray">
      {items.map((item) => (
        <div
          key={item.path}
          className={`composer-doc-chip${item.path === primaryPath ? " composer-doc-chip--primary" : ""}`}
          onClick={() => onSetPrimary(item.path)}
          role="button"
          tabIndex={0}
        >
          <span className="composer-doc-chip-bar" aria-hidden />
          <span className="composer-doc-chip-title">{item.title}</span>
          <button type="button" className="composer-chip-close" onClick={(e) => { e.stopPropagation(); onRemoveDoc(item.path); }} aria-label="移除">×</button>
        </div>
      ))}
      {pendingFiles.map((f) => (
        <div key={f.id} className="composer-file-chip">
          <span className="composer-file-icon">📄</span>
          <span>{f.name}</span>
          <span className="composer-file-size">{formatSize(f.size)}</span>
          <button type="button" className="composer-chip-close" onClick={() => onRemoveFile(f.id)} aria-label="移除">×</button>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: CSS（主文档左竖条）**

```css
.composer-doc-chip--primary .composer-doc-chip-bar {
  width: 3px;
  background: var(--accent);
}
.composer-doc-chip:not(.composer-doc-chip--primary) .composer-doc-chip-bar {
  width: 1px;
  background: var(--border-strong);
}
.composer-doc-chip--primary {
  background: var(--accent-soft);
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ComposerTray.tsx frontend/src/index.css
git commit -m "feat: ComposerTray with primary left bar doc chips"
```

---

## Task F4: `ComposerToolbar`（纯图标联网开关）

**Files:**
- Create: `frontend/src/components/ComposerToolbar.tsx`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: 实现工具行**

```tsx
function GlobeIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="12" cy="12" r="10" />
      <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

// webEnabled 按钮：无文字
<button
  type="button"
  className={`composer-icon-btn composer-web-btn${webEnabled ? " composer-web-btn--on" : ""}`}
  onClick={onToggleWeb}
  disabled={streaming}
  aria-pressed={webEnabled}
  aria-label={webEnabled ? "联网搜索：开" : "联网搜索：关"}
  title={webEnabled ? "联网搜索：开（本地优先，联网补充）" : "联网搜索：关（仅本地知识库）"}
>
  <GlobeIcon />
</button>
```

- [ ] **Step 2: CSS**

```css
.composer-icon-btn {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}
.composer-web-btn--on {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: var(--accent-border);
}
```

删除旧 `.chat-web-btn` / `.chat-web-btn--on` 绿色样式。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ComposerToolbar.tsx frontend/src/index.css
git commit -m "feat: ComposerToolbar with icon-only web toggle"
```

---

## Task F5: `api.ts` + `Chat.tsx` Composer 集成

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/components/Chat.tsx`

- [ ] **Step 1: 扩展 `chatStream`**

```typescript
export type ChatStreamOptions = {
  conversationId?: string | null;
  activeDocPaths?: string[];
  primaryDocPath?: string | null;
  webEnabled?: boolean;
  attachments?: string[];
};

export async function* chatStream(
  text: string,
  options: ChatStreamOptions = {},
): AsyncGenerator<ChatStreamEvent> {
  const {
    conversationId,
    activeDocPaths = [],
    primaryDocPath,
    webEnabled = false,
    attachments = [],
  } = options;
  // body: { text, conversation_id, active_doc_paths, primary_doc_path, web_enabled, attachments }
}
```

保留旧调用签名 overload 或更新 `Chat.tsx` 唯一调用点。

- [ ] **Step 2: `Chat` 附件随发送**

状态：

```typescript
const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
```

选文件 → `setPendingFiles` 追加（**不**立即 `uploadFile`）。

`send()` 流程：

```typescript
const uploaded: string[] = [];
for (const pf of pendingFiles) {
  const r = await uploadFile(pf.file, "未分类");
  uploaded.push(r.attachment);
}
setPendingFiles([]);
const userMsg: ChatMessage = {
  role: "user",
  text: display,
  ts: new Date().toISOString(),
  attachments: uploaded.length ? uploaded : undefined,
  doc_context: docPaths.length ? docPaths : undefined,
  primary_doc: primaryPath ?? undefined,
};
// 然后 chatStream(text, { activeDocPaths: docPaths, primaryDocPath: primaryPath, attachments: uploaded, ... })
```

删除旧 `onFile` 静默归档逻辑。

- [ ] **Step 3: 替换 `chat-input-bar` 为 Composer 卡片**

```tsx
<div className="composer-card">
  <ComposerTray ... />
  <div className="composer-input">
    <textarea ... />
  </div>
  <ComposerToolbar ... />
</div>
```

- [ ] **Step 4: Build + Commit**

```bash
cd frontend && npm run build
git add frontend/src/api.ts frontend/src/components/Chat.tsx
git commit -m "feat: Chat composer card, attach files on send, multi-doc API"
```

---

## Task F6: 下线合并专用 UI

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/DocViewer.tsx`
- Delete or orphan: `frontend/src/components/MergeConfigModal.tsx`（若无引用则删）
- Delete or orphan: `frontend/src/components/MergeSourceQuestion.tsx`
- Modify: `frontend/src/index.css`（删除 merge review bar 样式）

- [ ] **Step 1: `App.tsx` 移除**

删除：`selectionMode`、`selectedPaths`、`mergeReview`、`mergeSourceQuestion`、`handleMergeComplete`、`handleMergeAccept/Regenerate/Reject`、`getActiveMerge` effect、`activeMergeReview` prop 传递。

`DocViewer` 不再传 `mergeReview` 相关 props。

- [ ] **Step 2: `DocViewer` 移除审阅条**

删除：`mergeReview` props、`doc-merge-review-bar` footer、`mergeEditing` 分支、相关 overflow 菜单项。

- [ ] **Step 3: 清理未使用 import/API 调用**

`api.ts` 中 `acceptMerge` 等若仅合并 UI 使用，保留导出（测试/脚本可能用）或标 `@deprecated`。

- [ ] **Step 4: Build + Commit**

```bash
cd frontend && npm run build
git add frontend/src/App.tsx frontend/src/components/DocViewer.tsx
git commit -m "refactor: remove dedicated merge review UI; merge is chat-driven"
```

---

## Task F7: 样式收尾与消息气泡附件

**Files:**
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/components/Chat.tsx`

- [ ] **Step 1: `.composer-card` 容器**

```css
.composer-card {
  width: 100%;
  max-width: var(--chat-content-max-width);
  margin: 0 auto;
  padding: 0 20px 14px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-lg);
  background: var(--bg-surface);
  box-shadow: var(--shadow-sm);
}
.composer-input textarea {
  border: none;
  box-shadow: none;
  width: 100%;
  /* 去掉旧 chat-input-bar 双边框 */
}
.composer-tray {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
}
.composer-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 8px;
  border-top: 1px solid var(--border);
}
```

- [ ] **Step 2: 用户消息气泡展示 `doc_context` / `attachments` chip**

在 `renderMessageContent` 用户分支追加小型 chip 行（只读回放）。

- [ ] **Step 3: 全量 build + 手验**

```bash
cd frontend && npm run build
cd backend && python -m pytest -q
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/index.css frontend/src/components/Chat.tsx
git commit -m "style: composer card polish and message attachment chips"
```

---

## 验收自检

| Spec 验收项 | 对应 Task |
|------------|-----------|
| 三层 Composer 卡片 | F3, F4, F5, F7 |
| 托盘无标题、无添加按钮 | F3 |
| 主文档左竖条 | F3 |
| 主文档 ↔ 右侧栏 | F2 |
| 单击 / Ctrl+单击 | F2 |
| chip × 关闭 | F3, F2 |
| 纯图标联网、色彩开/关 | F4 |
| 附件 chip + 随发送 | F5 |
| `active_doc_paths` + `primary_doc_path` | B1, B2, F5 |
| 合并 UI 下线 | F6 |
| 合并删源 ask_user | B3 |
| 旧会话无 `doc_context` 不崩 | F5 手验 |

### 手验清单

- [ ] 单击侧栏文件 → 托盘 1 chip（主文档竖条）+ 右侧栏打开
- [ ] Ctrl+单击另一文件 → 托盘 2 chip，主文档不变
- [ ] 点击非主 chip → 主文档切换 + 右侧栏切换
- [ ] × 移除主文档 → 下一篇升主；托盘空 → 右侧栏关
- [ ] 选文件 → 托盘文件 chip；发送后用户气泡含附件
- [ ] 联网图标：关灰、开靛蓝；刷新保留
- [ ] 托盘 3 篇 +「合并成一篇」→ Agent 写新文档；出现 ask_user 删源
- [ ] 侧栏无「多选」按钮、无合并浮条

---

## Spec 覆盖自检

| Spec § | Task |
|--------|------|
| §5 Composer 结构 | F3–F7 |
| §5.2 联网纯图标 | F4 |
| §5.3 附件 | F5 |
| §6 托盘状态 | F1, F2, F3 |
| §7 目录树 | F2 |
| §8 合并模型化 | B3, F6 |
| §9 API | B1, B2, F5 |
| §11 测试 | B1, B2 + 手验清单 |

无 TBD / 占位符。
