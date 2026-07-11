# Doc Reader Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two doc-panel width tiers (narrow/wide) plus a focus-reading mode that hides chat and collapses the left sidebar.

**Architecture:** Keep layout state in `App.tsx` (`docWidth`, `docFocus`, `sidebarCollapsed`). `DocViewer` exposes header controls; CSS classes on `.app-shell` / `.doc-panel` / `.sidebar` drive layout. No backend changes. No new frontend test runner — verify manually per acceptance criteria.

**Tech Stack:** React + existing CSS in `frontend/src/index.css`

**Spec:** `docs/superpowers/specs/2026-07-11-doc-reader-layout-design.md`

---

## File map

| File | Responsibility |
|------|----------------|
| `frontend/src/App.tsx` | Own `docWidth` / `docFocus` / `sidebarCollapsed`; wire layout classes; Esc handler; pass callbacks to DocViewer/Sidebar |
| `frontend/src/components/DocViewer.tsx` | Header buttons: narrow⇄wide, enter/exit focus, close |
| `frontend/src/components/Sidebar.tsx` | Focus-mode collapsed rail + expand/collapse toggle |
| `frontend/src/index.css` | Width variants, focus shell, collapsed sidebar, focus body max-width, table overflow |

---

### Task 1: CSS — panel widths, focus shell, reading body

**Files:**
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Replace fixed `.doc-panel` width with modifiers**

Change the existing `.doc-panel` block (~line 242) so base styles have no fixed width, and add modifiers:

```css
.doc-panel {
  border-left: 1px solid var(--border);
  background: var(--bg-surface);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-panel);
  animation: slideInPanel 0.18s ease-out;
  min-height: 0;
}

.doc-panel--narrow {
  width: min(400px, 38vw);
  min-width: 300px;
}

.doc-panel--wide {
  width: min(720px, 58vw);
  min-width: 480px;
}

/* Focus: doc takes remaining space after sidebar */
.app-shell--doc-focus .doc-panel {
  flex: 1;
  width: auto;
  min-width: 0;
  border-left: none;
  box-shadow: none;
  animation: none;
}

.app-shell--doc-focus .main-panel {
  display: none;
}
```

- [ ] **Step 2: Collapsed sidebar + focus reading typography**

Add after `.sidebar` block (~line 266):

```css
.sidebar--collapsed {
  width: 40px;
  min-width: 40px;
}

.sidebar--collapsed .sidebar-section,
.sidebar--collapsed .sidebar-footer {
  display: none;
}

.sidebar-expand-rail {
  display: none;
  flex-direction: column;
  align-items: center;
  padding: 8px 0;
  height: 100%;
}

.sidebar--collapsed .sidebar-expand-rail {
  display: flex;
}

.sidebar-expand-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--border);
  background: var(--bg-surface);
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}

.sidebar-expand-btn:hover {
  background: var(--bg-hover);
  color: var(--text);
}

/* Focus mode: comfortable reading column + scrollable tables */
.app-shell--doc-focus .doc-viewer-body {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.app-shell--doc-focus .doc-viewer-body > * {
  width: 100%;
  max-width: 760px;
}

.app-shell--doc-focus .doc-markdown,
.doc-panel--wide .doc-markdown {
  overflow-x: auto;
}

.app-shell--doc-focus .doc-markdown table,
.doc-panel--wide .doc-markdown table {
  width: max-content;
  min-width: 100%;
}
```

- [ ] **Step 3: DocViewer header action button styles**

Add near `.doc-close-btn`:

```css
.doc-viewer-actions {
  display: flex;
  flex-shrink: 0;
  gap: 4px;
  margin-left: auto;
}

.doc-action-btn {
  flex-shrink: 0;
  height: 28px;
  padding: 0 8px;
  font-size: var(--font-ui-xs);
  line-height: 1;
  border: 1px solid var(--border);
  background: var(--bg-surface);
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  white-space: nowrap;
}

.doc-action-btn:hover {
  background: var(--bg-hover);
  color: var(--text);
}

.doc-action-btn.is-active {
  background: var(--accent-soft);
  border-color: var(--accent-border);
  color: var(--accent);
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/index.css
git commit -m "style: add doc panel width and focus-mode layout CSS"
```

---

### Task 2: DocViewer — header controls

**Files:**
- Modify: `frontend/src/components/DocViewer.tsx`

- [ ] **Step 1: Extend props**

```tsx
type DocWidth = "narrow" | "wide";

type Props = {
  path: string;
  refreshKey?: number;
  highlightText?: string;
  mode?: "panel" | "page";
  docWidth?: DocWidth;
  docFocus?: boolean;
  onClose: () => void;
  onToggleWidth?: () => void;
  onToggleFocus?: () => void;
};
```

- [ ] **Step 2: Render action buttons in header (panel mode)**

Replace the panel-mode header so close stays, and actions sit on the right:

```tsx
export function DocViewer({
  path,
  refreshKey = 0,
  highlightText,
  mode = "panel",
  docWidth = "narrow",
  docFocus = false,
  onClose,
  onToggleWidth,
  onToggleFocus,
}: Props) {
  // ... existing state/effects unchanged ...

  return (
    <div
      className={`doc-viewer${mode === "panel" ? " doc-viewer-panel" : ""}${
        docFocus ? " doc-viewer-focus" : ""
      }`}
    >
      <header className="doc-viewer-header">
        {mode === "panel" ? (
          <button type="button" className="doc-close-btn" onClick={onClose} title="关闭">
            ×
          </button>
        ) : (
          <button type="button" className="doc-back-btn" onClick={onClose}>
            ← 对话
          </button>
        )}
        <div className="doc-viewer-title">
          <span className="doc-path">{path}</span>
          <h2>{title}</h2>
        </div>
        {mode === "panel" && (
          <div className="doc-viewer-actions">
            {!docFocus && onToggleWidth && (
              <button
                type="button"
                className={`doc-action-btn${docWidth === "wide" ? " is-active" : ""}`}
                onClick={onToggleWidth}
                title={docWidth === "wide" ? "收窄侧栏" : "加宽侧栏"}
              >
                {docWidth === "wide" ? "窄栏" : "宽栏"}
              </button>
            )}
            {onToggleFocus && (
              <button
                type="button"
                className={`doc-action-btn${docFocus ? " is-active" : ""}`}
                onClick={onToggleFocus}
                title={docFocus ? "退出专注" : "专注阅读"}
              >
                {docFocus ? "退出专注" : "专注"}
              </button>
            )}
          </div>
        )}
      </header>
      {/* body unchanged */}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DocViewer.tsx
git commit -m "feat: add width and focus controls to DocViewer header"
```

---

### Task 3: Sidebar — focus collapse rail

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Add collapse props**

```tsx
type Props = {
  refreshKey?: number;
  selectedPath: string | null;
  activeConversationId: string | null;
  titleOverrides?: Record<string, string>;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  onSelectFile: (path: string) => void;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
};
```

- [ ] **Step 2: Render collapsed rail vs full sidebar**

```tsx
export function Sidebar({
  refreshKey = 0,
  selectedPath,
  activeConversationId,
  titleOverrides = {},
  collapsed = false,
  onToggleCollapsed,
  onSelectFile,
  onNewChat,
  onSelectConversation,
  onDeleteConversation,
}: Props) {
  // ... existing state/effects ...

  return (
    <aside className={`sidebar${collapsed ? " sidebar--collapsed" : ""}`}>
      {collapsed ? (
        <div className="sidebar-expand-rail">
          <button
            type="button"
            className="sidebar-expand-btn"
            title="展开侧栏"
            onClick={onToggleCollapsed}
          >
            »
          </button>
        </div>
      ) : (
        <>
          {/* existing sections unchanged */}
          {/* When onToggleCollapsed is provided (focus mode), show collapse control in tree head */}
          <section className="sidebar-section sidebar-tree-section">
            <div className="sidebar-section-head">
              <h4>知识库</h4>
              <div style={{ display: "flex", gap: 4 }}>
                {onToggleCollapsed && (
                  <button
                    type="button"
                    className="sidebar-refresh"
                    title="收起侧栏"
                    onClick={onToggleCollapsed}
                  >
                    «
                  </button>
                )}
                <button type="button" className="sidebar-refresh" onClick={refresh} title="刷新">
                  ↻
                </button>
              </div>
            </div>
            <FileTree
              paths={docs}
              selectedPath={selectedPath}
              onSelectFile={onSelectFile}
            />
          </section>
          <footer className="sidebar-footer">
            <ThemeToggle />
          </footer>
        </>
      )}
    </aside>
  );
}
```

Important: when `collapsed` is false, keep the **full** existing JSX (chat list + tree + footer). Only add the collapse button when `onToggleCollapsed` is defined. Prefer a small CSS class for the button group instead of inline `style` if easy (`sidebar-section-actions`).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Sidebar.tsx frontend/src/index.css
git commit -m "feat: support collapsed sidebar rail in focus mode"
```

---

### Task 4: App — state, layout wiring, Esc

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add state + handlers**

Update import: `import { useEffect, useState } from "react";`

```tsx
type DocWidth = "narrow" | "wide";

const [docWidth, setDocWidth] = useState<DocWidth>("narrow");
const [docFocus, setDocFocus] = useState(false);
const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

function closeDocPreview() {
  setPreviewPath(null);
  setHighlightText(undefined);
  setDocFocus(false);
  // docWidth intentionally retained
}

function enterDocFocus() {
  setDocFocus(true);
  setSidebarCollapsed(true);
}

function exitDocFocus() {
  setDocFocus(false);
  setSidebarCollapsed(false);
}

function toggleDocWidth() {
  setDocWidth((w) => (w === "narrow" ? "wide" : "narrow"));
}

function toggleDocFocus() {
  if (docFocus) exitDocFocus();
  else enterDocFocus();
}
```

- [ ] **Step 2: Esc key effect**

```tsx
useEffect(() => {
  if (!previewPath) return;
  function onKeyDown(e: KeyboardEvent) {
    if (e.key !== "Escape") return;
    e.preventDefault();
    if (docFocus) exitDocFocus();
    else closeDocPreview();
  }
  window.addEventListener("keydown", onKeyDown);
  return () => window.removeEventListener("keydown", onKeyDown);
}, [previewPath, docFocus]);
```

Note: wrap handlers in `useCallback` only if the project already does; otherwise define handlers above the effect and include stable logic inline to avoid stale closures (or disable exhaustive-deps carefully). Simplest: put the Esc logic inline in the effect using the current state values from the dependency array.

- [ ] **Step 3: Wire shell classes and children**

```tsx
return (
  <div
    className={`app-shell${docFocus && previewPath ? " app-shell--doc-focus" : ""}`}
  >
    <Sidebar
      refreshKey={sidebarRefreshKey}
      selectedPath={previewPath}
      activeConversationId={activeConversationId}
      titleOverrides={titleOverrides}
      collapsed={docFocus && previewPath ? sidebarCollapsed : false}
      onToggleCollapsed={
        docFocus && previewPath
          ? () => setSidebarCollapsed((c) => !c)
          : undefined
      }
      onSelectFile={(path) => openDocPreview(path)}
      onNewChat={() => {
        void newChat();
      }}
      onSelectConversation={selectConversation}
      onDeleteConversation={/* existing */}
    />
    <main className="main-panel">
      <Chat {...chatProps} />
    </main>
    {previewPath && (
      <aside
        className={`doc-panel doc-panel--${docFocus ? "narrow" : docWidth}${
          docFocus ? " doc-panel--focus" : ""
        }`}
      >
        <DocViewer
          path={previewPath}
          refreshKey={docRefreshKey}
          highlightText={highlightText}
          mode="panel"
          docWidth={docWidth}
          docFocus={docFocus}
          onClose={closeDocPreview}
          onToggleWidth={toggleDocWidth}
          onToggleFocus={toggleDocFocus}
        />
      </aside>
    )}
    {/* SearchSnippetModal unchanged */}
  </div>
);
```

Prefer cleaner class logic:

```tsx
className={
  docFocus
    ? "doc-panel doc-panel--focus"
    : `doc-panel doc-panel--${docWidth}`
}
```

And ensure CSS has `.doc-panel--focus` as alias for the focus flex rules (or rely solely on `.app-shell--doc-focus .doc-panel` from Task 1 — then no `--focus` modifier needed on the aside).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: wire doc width tiers and focus reading mode in App"
```

---

### Task 5: Manual verification

**Files:** none (browser)

- [ ] **Step 1: Start frontend** (if not running)

```powershell
# from repo root, or use existing lorechat.ps1 / vite
cd frontend; npm run dev
```

- [ ] **Step 2: Acceptance checklist**

1. Open a doc with a table → opens **narrow** side panel; chat still usable.
2. Click **宽栏** → panel widens (~58vw / 720px); chat still visible and scrollable; send still works.
3. Click **窄栏** → back to narrow.
4. Click **专注** → chat hidden; left sidebar collapsed to ~40px rail; doc fills space; body ~760px centered; tables scroll horizontally if needed.
5. Click **»** on rail → sidebar expands; pick another file → preview updates.
6. Click **«** → sidebar collapses again.
7. Click **退出专注** → returns to previous narrow/wide tier (not always narrow).
8. Press **Esc** in focus → exits focus (doc still open).
9. Press **Esc** again → closes doc.
10. Re-open a doc → remembers last **narrow/wide** choice; focus is off.

- [ ] **Step 3: Fix any visual gaps** (button overflow in header, min-width crushing chat on small windows) then commit if needed.

```bash
git add frontend/src
git commit -m "fix: polish doc reader layout edge cases"
```

---

## Spec coverage check

| Spec requirement | Task |
|------------------|------|
| Narrow/wide side panel | 1, 2, 4 |
| Remember `docWidth` after close | 4 (`closeDocPreview`) |
| Focus hides chat | 1 (`.app-shell--doc-focus .main-panel`), 4 |
| Sidebar collapses on each focus enter | 3, 4 (`enterDocFocus`) |
| Exit focus restores width tier | 4 (`exitDocFocus` keeps `docWidth`) |
| Esc behavior | 4 |
| Table horizontal scroll + max-width body | 1 |
| No drag resize / no backend | N/A (out of scope) |
