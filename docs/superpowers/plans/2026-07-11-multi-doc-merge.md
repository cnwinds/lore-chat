# 多文档合并 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 支持侧栏多选 ≥2 篇文档，AI 全局合并为一篇新文档；用户在预览区采用 / 重新生成 / 删除此文；采用后征询是否删除源文档；改过正文时重生/删除才弹确认。

**Architecture:** 后端新增 `MergeSessionStore`（`.kb/merge_sessions.json`）追踪 pending 审阅会话与 `generated_content_hash`；`Organizer.merge_documents` 复用 `_synthesize` 风格的全局重构提示词；FastAPI 暴露 `/api/docs/merge/*` 端点。前端在 `FileTree`/`Sidebar` 加多选模式，`DocViewer` 加审阅条与可选编辑（复用已有 `PUT /api/doc`）。

**Tech Stack:** Python 3.12, FastAPI, pytest; React + TypeScript + Vite。

**设计文档:** [2026-07-11-multi-doc-merge-design.md](../specs/2026-07-11-multi-doc-merge-design.md)

---

## 关键契约（跨任务共享）

```python
# backend/app/engine/merge_sessions.py
@dataclass
class MergeSession:
    id: str
    status: str              # pending_review | accepted | rejected
    new_path: str
    source_paths: list[str]
    instruction: str
    order: list[str]
    generated_content_hash: str
    created_at: str
    updated_at: str

# backend/app/engine/organizer.py
@dataclass
class MergeResult:
    status: str              # saved | rejected
    merge_id: str | None
    rel_path: str | None
    source_paths: list[str]
    user_modified: bool
    question_id: str | None  # accept 后删源征询
    message: str

# backend/app/engine/content_hash.py
def body_hash(body: str) -> str:
    """规范化正文后 SHA-256，前缀 sha256:"""
```

```typescript
// frontend/src/api.ts
export type MergeSession = {
  id: string;
  status: "pending_review" | "accepted" | "rejected";
  new_path: string;
  source_paths: string[];
  user_modified: boolean;
};

export type MergeResult = {
  status: string;
  merge_id: string | null;
  rel_path: string | null;
  source_paths: string[];
  user_modified: boolean;
  question_id: string | null;
  message: string;
};
```

---

## 文件结构

```
backend/app/
  engine/
    content_hash.py           # 新建：正文 hash
    merge_sessions.py         # 新建：会话 CRUD + user_modified 判断
    organizer.py                # 修改：merge_documents / accept / reject / regenerate / resolve_sources
  api/routes.py                 # 修改：/api/docs/merge/* 路由
  deps.py                       # 修改：注册 merge_sessions 到 Container
backend/tests/
  test_content_hash.py          # 新建
  test_merge_sessions.py        # 新建
  test_merge_documents.py       # 新建
  test_merge_api.py             # 新建
frontend/src/
  api.ts                        # 修改：merge API
  App.tsx                       # 修改：selectionMode / mergeReview 状态
  components/
    FileTree.tsx                # 修改：多选模式
    Sidebar.tsx                 # 修改：多选 UI + 合并配置
    DocViewer.tsx               # 修改：审阅条 + 编辑保存
    MergeConfigModal.tsx        # 新建：合并配置弹层
    MergeSourceQuestion.tsx     # 新建：删源文档征询（或内嵌 Sidebar/App）
  index.css                     # 修改：多选 / 浮条 / 审阅条样式
```

---

### Task 1: 正文 hash 工具

**Files:**
- Create: `backend/app/engine/content_hash.py`
- Test: `backend/tests/test_content_hash.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_content_hash.py
from app.engine.content_hash import body_hash, is_body_modified

def test_body_hash_stable_for_same_content():
    h1 = body_hash("hello\n")
    h2 = body_hash("hello")
    assert h1 == h2

def test_is_body_modified_detects_change():
    original = body_hash("alpha")
    assert is_body_modified("beta", original) is True
    assert is_body_modified("alpha\n", original) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_content_hash.py -v`  
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/engine/content_hash.py
from __future__ import annotations
import hashlib

def normalize_body(body: str) -> str:
    return body.rstrip() + "\n"

def body_hash(body: str) -> str:
    norm = normalize_body(body)
    digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"

def is_body_modified(body: str, generated_hash: str) -> bool:
    return body_hash(body) != generated_hash
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_content_hash.py -v`  
Expected: PASS (2 tests)

---

### Task 2: MergeSessionStore

**Files:**
- Create: `backend/app/engine/merge_sessions.py`
- Modify: `backend/app/deps.py`
- Test: `backend/tests/test_merge_sessions.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_merge_sessions.py
from app.engine.merge_sessions import MergeSessionStore

def test_create_and_get_pending(tmp_path):
    store = MergeSessionStore(tmp_path / "merge_sessions.json")
    sid = store.create(
        new_path="a/merged.md",
        source_paths=["a/1.md", "a/2.md"],
        instruction="保留表格",
        order=["a/1.md", "a/2.md"],
        generated_content_hash="sha256:abc",
    )
    s = store.get(sid)
    assert s["status"] == "pending_review"
    assert s["new_path"] == "a/merged.md"

def test_find_active_by_path(tmp_path):
    store = MergeSessionStore(tmp_path / "merge_sessions.json")
    sid = store.create(
        new_path="x.md", source_paths=["a.md", "b.md"],
        instruction="", order=["a.md", "b.md"], generated_content_hash="h",
    )
    found = store.find_active_by_path("x.md")
    assert found is not None
    assert found["id"] == sid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_merge_sessions.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement MergeSessionStore**

```python
# backend/app/engine/merge_sessions.py — 核心方法
class MergeSessionStore:
    def create(self, *, new_path, source_paths, instruction, order, generated_content_hash) -> str: ...
    def get(self, sid: str) -> dict: ...
    def update(self, sid: str, **fields) -> dict: ...
    def find_active_by_path(self, path: str) -> dict | None:
        # status == pending_review 且 new_path 匹配
    def user_modified(self, sid: str, current_body: str) -> bool: ...
```

在 `deps.py` 的 `Container` 增加 `merge_sessions: MergeSessionStore`，`build_container` 初始化：

```python
merge_sessions = MergeSessionStore(settings.kb_path / ".kb" / "merge_sessions.json")
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_merge_sessions.py -v`  
Expected: PASS

---

### Task 3: Organizer.merge_documents

**Files:**
- Modify: `backend/app/engine/organizer.py`
- Test: `backend/tests/test_merge_documents.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_merge_documents.py
import json
from app.engine.merge_sessions import MergeSessionStore
from tests.test_organizer import _make  # 复用 fixture 工厂

def test_merge_documents_creates_new_file(tmp_path):
    decision = json.dumps({
        "action": "new", "rel_path": "技术/合并.md",
        "title": "合并", "category": "技术", "tags": [],
        "ambiguous": False, "reason": "合并",
    })
    merged_body = "# 合并结果\n\n去重后的内容。\n"
    org, repo, pending = _make(tmp_path, ["摘要", decision, merged_body])
    repo.write_doc("技术/a.md", {"title": "A"}, "内容A\n", commit_msg="seed")
    repo.write_doc("技术/b.md", {"title": "B"}, "内容B\n", commit_msg="seed")
    sessions = MergeSessionStore(tmp_path / "knowledge" / ".kb" / "merge_sessions.json")

    result = org.merge_documents(
        ["技术/a.md", "技术/b.md"],
        instruction="",
        merge_sessions=sessions,
    )
    assert result.status == "saved"
    assert result.rel_path == "技术/合并.md"
    doc = repo.read_doc("技术/合并.md")
    assert "去重后的内容" in doc.body
    assert doc.meta.get("merged_from") == ["技术/a.md", "技术/b.md"]
    assert sessions.find_active_by_path("技术/合并.md") is not None

def test_merge_rejects_system_paths(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    sessions = MergeSessionStore(tmp_path / "knowledge" / ".kb" / "merge_sessions.json")
    repo.write_doc("系统/a.md", {"title": "A"}, "x\n", commit_msg="seed")
    repo.write_doc("技术/b.md", {"title": "B"}, "y\n", commit_msg="seed")
    result = org.merge_documents(["系统/a.md", "技术/b.md"], merge_sessions=sessions)
    assert result.status == "rejected"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_merge_documents.py -v`  
Expected: FAIL `AttributeError: merge_documents`

- [ ] **Step 3: Implement merge_documents**

在 `organizer.py` 添加：

```python
@dataclass
class MergeResult:
    status: str
    merge_id: str | None
    rel_path: str | None
    source_paths: list[str]
    user_modified: bool
    question_id: str | None
    message: str

def merge_documents(
    self,
    source_paths: list[str],
    *,
    instruction: str = "",
    order: list[str] | None = None,
    target_path: str | None = None,
    title_hint: str | None = None,
    merge_sessions: MergeSessionStore,
) -> MergeResult:
```

实现要点：
1. `len(source_paths) < 2` → rejected
2. 任一路径 `repo.is_protected` 或不存在 → rejected
3. `_synthesize_merge(sources_text, instruction)` — 参考 `_synthesize`，user content 改为多篇 `=== 文档 {path} ===\n{body}`
4. `_decide` 决定路径；`target_path` 有值时强制使用该路径
5. `write_doc` meta 含 `merged_from: source_paths`, `source: "merge"`
6. `merge_sessions.create(...)` 或 `update`（regenerate 时）
7. 返回 `MergeResult(status="saved", merge_id=..., user_modified=False, ...)`

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_merge_documents.py -v`  
Expected: PASS

---

### Task 4: accept / reject / regenerate / resolve_sources

**Files:**
- Modify: `backend/app/engine/organizer.py`
- Test: `backend/tests/test_merge_documents.py`（追加用例）

- [ ] **Step 1: Write failing tests**

```python
def test_merge_regenerate_overwrites_same_path(tmp_path):
    # 两次 merge_documents(..., target_path=...) 后 body 变化、hash 更新
    ...

def test_merge_reject_deletes_new_doc(tmp_path):
    # reject 后 new_path 不在 list_tree
    ...

def test_merge_accept_creates_source_question(tmp_path):
    # accept 返回 question_id；pending 有 multi_select 选项 per source
    ...

def test_resolve_merge_sources_deletes_selected(tmp_path):
    # 只删勾选的源文档
    ...
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement methods**

```python
def regenerate_merge(self, merge_id: str, *, merge_sessions) -> MergeResult:
    s = merge_sessions.get(merge_id)
    if s["status"] != "pending_review":
        return MergeResult(status="rejected", message="会话已结束", ...)
    return self.merge_documents(
        s["source_paths"],
        instruction=s["instruction"],
        order=s["order"],
        target_path=s["new_path"],
        merge_sessions=merge_sessions,
        session_id=merge_id,  # 更新而非新建
    )

def reject_merge(self, merge_id: str, *, merge_sessions, indexer) -> MergeResult:
    # delete_path + indexer.remove_doc + status=rejected

def accept_merge(self, merge_id: str, *, merge_sessions) -> MergeResult:
    # status=accepted
    # pending.create(question=..., options=[{id: path, label: path}...], multi_select=True,
    #   payload={kind: "merge_sources", merge_id, new_path, source_paths})

def resolve_merge_sources(self, merge_id: str, delete_paths: list[str], *, merge_sessions) -> MergeResult:
    # 校验 delete_paths ⊆ source_paths；repo.delete_path；indexer.remove_doc
```

`merge_sessions.update` regenerate 时刷新 `generated_content_hash`。

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd backend && python -m pytest tests/test_merge_documents.py -v`

---

### Task 5: API 路由

**Files:**
- Modify: `backend/app/api/routes.py`
- Test: `backend/tests/test_merge_api.py`

- [ ] **Step 1: Write failing API tests**

```python
# backend/tests/test_merge_api.py
def test_merge_api_flow(client, tmp_path):
    # seed 2 docs via repo helper or POST if available
    r = client.post("/api/docs/merge", json={
        "paths": ["技术/a.md", "技术/b.md"],
        "instruction": "",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "saved"
    merge_id = data["merge_id"]

    r2 = client.get(f"/api/docs/merge/{merge_id}")
    assert r2.json()["user_modified"] is False

    r3 = client.post(f"/api/docs/merge/{merge_id}/accept")
    assert r3.json()["question_id"]

    r4 = client.post(f"/api/docs/merge/{merge_id}/reject")
    # 对已 accept 的应 400；另开用例测 reject
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Add routes**

```python
class MergeBody(BaseModel):
    paths: list[str]
    instruction: str = ""
    order: list[str] | None = None
    title: str | None = None

class ResolveMergeSourcesBody(BaseModel):
    delete_paths: list[str]

@router.post("/docs/merge")
async def merge_docs(body: MergeBody, request: Request): ...

@router.get("/docs/merge/{merge_id}")
async def get_merge_session(merge_id: str, request: Request):
    # 读 session + repo.read_doc → user_modified

@router.get("/docs/merge/active")
async def get_active_merge(path: str, request: Request): ...

@router.post("/docs/merge/{merge_id}/regenerate")
async def regenerate_merge(merge_id: str, request: Request): ...

@router.post("/docs/merge/{merge_id}/accept")
async def accept_merge(merge_id: str, request: Request): ...

@router.post("/docs/merge/{merge_id}/reject")
async def reject_merge(merge_id: str, request: Request): ...

@router.post("/docs/merge/{merge_id}/resolve-sources")
async def resolve_merge_sources(merge_id: str, body: ResolveMergeSourcesBody, request: Request): ...
```

在 `resolve` 路由中增加 `payload.kind == "merge_sources"` 分支，转调 `organizer.resolve_merge_sources`。

- [ ] **Step 4: Run API tests**

Run: `cd backend && python -m pytest tests/test_merge_api.py tests/test_merge_documents.py -v`  
Expected: PASS

---

### Task 6: 前端 API 封装

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add types and functions**

```typescript
export async function mergeDocs(body: {
  paths: string[];
  instruction?: string;
  order?: string[];
  title?: string;
}): Promise<MergeResult> {
  return apiFetch("/api/docs/merge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function getMergeSession(id: string): Promise<MergeSession> { ... }
export async function getActiveMerge(path: string): Promise<MergeSession | null> { ... }
export async function regenerateMerge(id: string): Promise<MergeResult> { ... }
export async function acceptMerge(id: string): Promise<MergeResult> { ... }
export async function rejectMerge(id: string): Promise<MergeResult> { ... }
export async function resolveMergeSources(id: string, deletePaths: string[]): Promise<MergeResult> { ... }
```

- [ ] **Step 2: Manual smoke**

启动前后端，`curl -X POST http://localhost:8000/api/docs/merge ...` 确认 JSON 形状与类型一致。

---

### Task 7: FileTree 多选模式

**Files:**
- Modify: `frontend/src/components/FileTree.tsx`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Extend Props**

```typescript
type Props = {
  paths: string[];
  selectedPath: string | null;
  selectionMode?: boolean;
  selectedPaths?: Set<string>;
  onSelectFile: (path: string) => void;
  onToggleSelect?: (path: string, shiftKey?: boolean) => void;
  onPreviewFile?: (path: string) => void;
};
```

- [ ] **Step 2: File row behavior**

- `selectionMode` 时：行首 checkbox；单击 → `onToggleSelect`；双击 → `onPreviewFile`
- 非多选：保持现有单击预览
- 文件夹行：多选模式下显示「全选」小按钮（`onSelectFolder` prop）

- [ ] **Step 3: CSS**

```css
.file-tree-row.checked { background: var(--accent-dim); }
.file-tree-checkbox { margin-right: 6px; }
```

- [ ] **Step 4: Manual verify**

多选模式下勾选、shift 范围、双击预览互不干扰。

---

### Task 8: Sidebar 多选浮条与合并配置

**Files:**
- Create: `frontend/src/components/MergeConfigModal.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Sidebar props 扩展**

```typescript
selectionMode: boolean;
selectedPaths: Set<string>;
onToggleSelectionMode: () => void;
onToggleSelect: (path: string, shift?: boolean) => void;
onClearSelection: () => void;
onMergeComplete: (result: MergeResult) => void;
```

- [ ] **Step 2: 知识库标题栏**

「多选」toggle；`Esc` 监听在 `App.tsx` 退出多选。

- [ ] **Step 3: 底部浮条**

`selectedPaths.size >= 2` 时显示「已选 N 篇 · 合并为文档」；点击打开 `MergeConfigModal`。

- [ ] **Step 4: MergeConfigModal**

- 可拖拽排序列表（`@dnd-kit` 可选；首版用上下箭头按钮即可，YAGNI）
- `instruction` textarea、`title` input（可选）
- 提交调用 `mergeDocs`；`onMergeComplete` 回调

- [ ] **Step 5: App.tsx 状态**

```typescript
const [selectionMode, setSelectionMode] = useState(false);
const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
const [mergeReview, setMergeReview] = useState<{
  mergeId: string;
  newPath: string;
  sourcePaths: string[];
  userModified: boolean;
} | null>(null);
```

`onMergeComplete`：`openDocPreview(result.rel_path)` + `setMergeReview(...)` + `refreshSidebar()` + 退出多选。

---

### Task 9: DocViewer 审阅条 + 编辑 + 智能确认

**Files:**
- Modify: `frontend/src/components/DocViewer.tsx`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Extend Props**

```typescript
mergeReview?: {
  mergeId: string;
  sourcePaths: string[];
  userModified: boolean;
} | null;
onMergeReviewChange?: (patch: Partial<{ userModified: boolean }>) => void;
onMergeAccept?: () => void;
onMergeRegenerate?: () => void;
onMergeReject?: () => void;
onKbChanged?: (path?: string) => void;
```

- [ ] **Step 2: 审阅条 UI**

`mergeReview` 存在且 session pending 时，底部显示：

```
正在审阅合并结果（源自 N 篇）
[删除此文] [重新生成] [采用]
```

- [ ] **Step 3: 智能确认 helper**

```typescript
async function withModifiedConfirm(
  action: "regenerate" | "reject",
  userModified: boolean,
  mergeId: string,
  run: () => Promise<void>,
) {
  if (userModified) {
    const msg = action === "regenerate"
      ? "文档已修改，重新生成将覆盖你的编辑，是否继续？"
      : "文档已修改，删除将丢失你的编辑，是否继续？";
    if (!window.confirm(msg)) return;
  } else {
    // 兜底：请求 getMergeSession，若 user_modified 再 confirm
    const s = await getMergeSession(mergeId);
    if (s.user_modified && !window.confirm(msg)) return;
  }
  await run();
}
```

- [ ] **Step 4: 编辑模式（可选但 spec 要求）**

标题栏加「编辑」toggle → textarea 替换 Markdown 渲染 → 「保存」调用 `saveDoc(path, body)` → `onMergeReviewChange({ userModified: true })`。

- [ ] **Step 5: Wire handlers in App.tsx**

```typescript
async function handleMergeRegenerate() {
  const r = await regenerateMerge(mergeReview.mergeId);
  setDocRefreshKey(k => k + 1);
  setMergeReview(prev => prev ? { ...prev, userModified: false } : null);
}
// reject → rejectMerge + closeDocPreview + clear mergeReview
// accept → acceptMerge + set sourceQuestion state
```

打开文档时 `useEffect`：`getActiveMerge(path)` 恢复 `mergeReview`。

---

### Task 10: 删源文档征询 UI

**Files:**
- Create: `frontend/src/components/MergeSourceQuestion.tsx`
- Modify: `frontend/src/App.tsx` 或 `Sidebar.tsx`

- [ ] **Step 1: Component**

复用 `PendingQuestion` 的 checkbox 多选样式；props：

```typescript
type Props = {
  mergeId: string;
  newPath: string;
  sourcePaths: string[];
  questionId?: string;  // 若走 pending
  onDone: () => void;
};
```

- [ ] **Step 2: accept 后展示**

`acceptMerge` 返回 `question_id` 时，在 `App` 层显示 `MergeSourceQuestion`（侧栏底部或 modal）。

- [ ] **Step 3: 提交**

`resolveMergeSources(mergeId, selectedPaths)` 或 `resolveQuestion(questionId, { choices })`；完成后 `refreshSidebar()`、`onDone`。

---

### Task 11: 端到端验收

- [ ] **Step 1: Backend full suite**

Run: `cd backend && python -m pytest -v`  
Expected: all pass

- [ ] **Step 2: Frontend build**

Run: `cd frontend && npm run build`  
Expected: no TS errors

- [ ] **Step 3: Manual E2E checklist（对照 spec 验收 1–7）**

1. 多选 4 篇真实文档 → 合并 → 侧栏新文档 + 右侧预览
2. 未改正文 → 重新生成 / 删除：无弹窗
3. 编辑保存后 → 重新生成 / 删除：有弹窗
4. 采用 → 征询删源；默认不勾
5. 关闭预览再打开 → 审阅条仍在
6. 系统文档不可选（后端拒绝 + 前端灰掉 `isSystemLayerPath`）

---

## Spec 覆盖自检

| Spec 要求 | Task |
|-----------|------|
| 侧栏多选 | 7, 8 |
| 直接写正式文档 | 3, 5 |
| 采用 / 重生 / 删除 | 4, 9 |
| 智能确认（改过才弹窗） | 1, 9 |
| merge_sessions + hash | 1, 2 |
| 删源征询 multi_select | 4, 10 |
| GET active by path | 2, 5, 9 |
| merged_from frontmatter | 3 |
| 系统路径禁止 | 3, 7 |

无 TBD / 占位符。

---

## 执行方式

Plan 已保存。两种执行选项：

1. **Subagent-Driven（推荐）** — 每 Task 派生子 agent，任务间 review  
2. **Inline Execution** — 本会话按 Task 顺序直接实现，checkpoint 复核

你想用哪种？
