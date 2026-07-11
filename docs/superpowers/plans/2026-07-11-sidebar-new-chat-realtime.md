# Sidebar New Chat Realtime Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clicking「新建」immediately shows (or reuses) an empty conversation in the sidebar; first user question optimistically updates the title.

**Architecture:** Frontend-driven. `App.newChat` lists conversations, reuses `message_count === 0` or creates via API, then refreshes sidebar. `Chat` notifies App of first-question title; Sidebar applies title overrides until server refresh on stream `done`.

**Tech Stack:** React + existing `/api/conversations` endpoints

---

### Task 1: Shared title helper

**Files:**
- Modify: `frontend/src/api.ts` (or small util next to it)

- [x] Add `titleFromText(text: string): string` matching backend `_title_from_text` (first line, max 40 + `…`)

### Task 2: App — newChat create/reuse + title override

**Files:**
- Modify: `frontend/src/App.tsx`

- [x] `newChat`: `listConversations` → find empty → reuse or `createConversation` → set active + refresh
- [x] State `titleOverrides: Record<string, string>`; clear on sidebar refresh / delete
- [x] Pass `titleOverrides` + `onFirstQuestionTitle` to children

### Task 3: Sidebar — apply title overrides

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx`

- [x] Accept `titleOverrides`; render `titleOverrides[c.id] ?? c.title`

### Task 4: Chat — notify on first question

**Files:**
- Modify: `frontend/src/components/Chat.tsx`

- [x] Prop `onFirstQuestionTitle?(id, title)`
- [x] In `runAgentStream`, before/when ensuring cid: if no prior user msgs, call with `titleFromText(display)`
- [x] Keep `ensureConversationId` for lazy create path

### Task 5: Manual verify

- [ ] New → sidebar shows「新对话」
- [ ] New again (empty) → same id
- [ ] First question → title updates immediately
- [ ] Stream done → list refresh aligns
