# 前端 God Component 拆分实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现。步骤用 `- [ ]` 跟踪。本计划以**表征测试 + 纯函数单测**替代全链路 TDD；每步提取后必须 `npm run test` + `npm run build` 通过，再提交。

**Goal:** 将 `Chat.tsx`（678 行）、`DocViewer.tsx`（829 行）、`App.tsx`（549 行）拆为职责单一的小模块，**不改变任何用户可见行为**。

**Architecture:** 「安全网先行 → 自底向上提取」：先加 Vitest 与纯函数测试，再抽 hooks/utils，最后抽 presentational 子组件；`App` 最后动（它编排 Doc 浮窗/侧栏/合并审阅，依赖前两者的稳定接口）。禁止大爆炸重写；每任务只移动代码、不改逻辑。

**Tech Stack:** React 19 + TypeScript + Vite；新增 Vitest + @testing-library/react + jsdom。

**关联:** [2026-07-12-architecture-fixes.md](./2026-07-12-architecture-fixes.md) 决策表已将本项 defer；本计划独立执行，不与架构修复计划混在同一 PR。

---

## 现状与职责地图

| 文件 | 行数 | 纠缠的职责 |
|------|------|------------|
| `Chat.tsx` | 678 | 会话历史加载、SSE 流式、归档沉淀、附件上传、滚动粘底、消息渲染、联网开关 |
| `DocViewer.tsx` | 829 | 文档加载/刷新、dirty 状态机、未保存弹窗、预览/Markdown 切换、大纲跳转、高亮摘录、合并审阅栏、工具栏 |
| `App.tsx` | 549 | 侧栏/对话/文档三栏编排、Doc 浮窗 vs 固定、专注模式、多选合并、合并审阅 API、全局 Esc、prop 钻孔 |

已有子组件（`DocLivePreview`、`TimelineBlockView`、`Sidebar` 等）质量尚可；问题集中在三个「容器」文件。

---

## 决策记录（实现前已定）

| 项 | 决策 |
|----|------|
| 是否改 UI/交互 | **否**，纯结构重构 |
| 状态管理库 | **不引入** Redux/Zustand；用 custom hooks + 可选 React Context |
| 执行顺序 | **Chat → DocViewer → App**（App 依赖前两者 props 稳定） |
| Context 范围 | 仅在 Task A3 为 Doc 预览状态引入 `DocPreviewContext`，避免 Chat 继续收 6+ 回调 |
| 目标行数 | 每个原 God 文件 **≤ 200 行**（编排层），逻辑进 hooks/utils |
| 测试策略 | 纯函数 100% 单测；hooks 用 RTL `renderHook`；**不做** E2E（成本高） |
| Sidebar | **本计划不拆**（231 行，边界清晰） |
| 并行 PR | 允许按 Phase 分 3 个 PR，但 Phase 0 必须是第一个 PR 的基础 |

---

## 目标目录结构（完成后）

```
frontend/src/
  types/
    doc.ts                    # DocWidth, DocMode, EditMode
  contexts/
    DocPreviewContext.tsx     # 预览路径、pin/focus/width、open/close
  hooks/
    chat/
      useChatScroll.ts
      useChatConversation.ts
      useAgentStream.ts
    doc/
      useDocLoader.ts
      useDocDirtyPrompt.ts
      useDocHighlight.ts
    app/
      useMergeReviewSession.ts
      useKbFileSelection.ts
  utils/
    chatMessage.ts            # 从 Chat 抽出
    docStorage.ts             # editMode sessionStorage
    docReadOnly.ts
  components/
    chat/
      ChatMessageList.tsx
      ChatMessageRow.tsx
      ChatInputBar.tsx
    doc/
      DocViewerHeader.tsx
      DocViewerBody.tsx
      DocMergeReviewBar.tsx
    app/
      AppShell.tsx
      DocFloatLayer.tsx
      DocPinnedPanel.tsx
    Chat.tsx                  # 薄编排 ~150 行
    DocViewer.tsx             # 薄编排 ~180 行
  App.tsx                     # 薄编排 ~120 行
```

---

## 手动冒烟清单（每个 Phase 结束必跑）

在浏览器中逐项确认（无自动化替代前这是回归底线）：

1. 新建对话 → 首问流式输出 → 侧边栏标题更新
2. 联网开关切换后发送，请求带 `web_enabled`
3. 点击 KB 来源打开浮窗 Doc → pin 到右侧 → 专注模式 → Esc 退出
4. 编辑 Doc dirty → 切换文件触发未保存弹窗 → 保存/放弃/取消 三条路径
5. 合并审阅：采用 / 重新生成 / 删除，及 `MergeSourceQuestion` 弹窗
6. 多选文件合并 → 预览合并结果
7. Ctrl+S 保存文档；Ctrl+Enter 发送消息

---

# Phase 0：测试安全网

## Task 0: 安装 Vitest 与测试脚本

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`

- [ ] **Step 1: 安装依赖**

```bash
cd frontend
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

- [ ] **Step 2: 新增 `vitest.config.ts`**

```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
```

- [ ] **Step 3: 新增 `src/test/setup.ts`**

```typescript
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 4: 修改 `package.json` scripts**

```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 5: 验证空套件通过**

```bash
cd frontend && npm run test
```

Expected: `Tests  no tests` 或 0 tests, exit 0

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/src/test/setup.ts
git commit -m "chore(frontend): add vitest and testing-library"
```

---

## Task 1: 抽出并测试 Chat 纯函数

**Files:**
- Create: `frontend/src/utils/chatMessage.ts`
- Create: `frontend/src/utils/chatMessage.test.ts`
- Modify: `frontend/src/components/Chat.tsx`（改为 import，逻辑不变）

- [ ] **Step 1: 写失败测试 `chatMessage.test.ts`**

```typescript
import { describe, expect, it } from "vitest";
import {
  formatMessageTs,
  markToolBlockResolved,
  kbPathFromToolResult,
} from "./chatMessage";
import type { ChatMessage } from "../api";

describe("formatMessageTs", () => {
  it("formats valid ISO time in zh-CN 24h", () => {
    const out = formatMessageTs("2026-07-12T14:30:00.000Z");
    expect(out).toMatch(/^\d{2}:\d{2}$/);
  });

  it("returns empty for invalid", () => {
    expect(formatMessageTs("not-a-date")).toBe("");
  });
});

describe("markToolBlockResolved", () => {
  it("patches matching tool block in timeline", () => {
    const msgs: ChatMessage[] = [
      {
        role: "assistant",
        timeline: [
          { type: "tool", id: "t1", tool: "ask_user", status: "pending" },
        ],
      },
    ];
    const next = markToolBlockResolved(msgs, "t1", "选项 A");
    expect(next[0].timeline?.[0]).toMatchObject({
      choice_resolved: "选项 A",
    });
  });
});

describe("kbPathFromToolResult", () => {
  it("returns kb path from sources", () => {
    const path = kbPathFromToolResult({
      sources: [{ type: "kb", path: "foo/bar.md" }],
    });
    expect(path).toBe("foo/bar.md");
  });
});
```

- [ ] **Step 2: 运行确认失败**

```bash
cd frontend && npm run test -- src/utils/chatMessage.test.ts
```

Expected: FAIL — module not found

- [ ] **Step 3: 实现 `chatMessage.ts`（从 Chat.tsx 剪切，不改实现）**

```typescript
import type { ChatMessage, SourceRef, TimelineBlock } from "../api";

export function kbPathFromToolResult(
  data: Record<string, unknown>,
): string | undefined {
  const sources = data.sources as SourceRef[] | undefined;
  const kb = sources?.find((s) => s.type === "kb");
  return kb?.path;
}

export function formatMessageTs(ts: string): string {
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return "";
  }
}

export function markToolBlockResolved(
  messages: ChatMessage[],
  blockId: string,
  choiceLabel: string,
): ChatMessage[] {
  function patchBlock(block: TimelineBlock): TimelineBlock {
    if (block.type === "tool" && block.id === blockId) {
      return { ...block, choice_resolved: choiceLabel };
    }
    if (block.type === "parallel") {
      return {
        ...block,
        children: block.children.map(patchBlock),
      };
    }
    return block;
  }
  return messages.map((msg) =>
    msg.timeline ? { ...msg, timeline: msg.timeline.map(patchBlock) } : msg,
  );
}
```

- [ ] **Step 4: Chat.tsx 删除本地定义，改为 `import { ... } from "../utils/chatMessage"`**

- [ ] **Step 5: 测试通过 + build**

```bash
cd frontend && npm run test -- src/utils/chatMessage.test.ts && npm run build
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/utils/chatMessage.ts frontend/src/utils/chatMessage.test.ts frontend/src/components/Chat.tsx
git commit -m "refactor(chat): extract chatMessage utils with tests"
```

---

## Task 2: 抽出并测试 Doc 纯函数

**Files:**
- Create: `frontend/src/types/doc.ts`
- Create: `frontend/src/utils/docReadOnly.ts`
- Create: `frontend/src/utils/docStorage.ts`
- Create: `frontend/src/utils/docReadOnly.test.ts`
- Create: `frontend/src/utils/docStorage.test.ts`
- Modify: `frontend/src/components/DocViewer.tsx`
- Modify: `frontend/src/App.tsx`（`DocWidth` 改从 types 导入）

- [ ] **Step 1: 写失败测试**

`docReadOnly.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { isReadOnlyPath } from "./docReadOnly";

describe("isReadOnlyPath", () => {
  it("treats .kb/ as read-only", () => {
    expect(isReadOnlyPath(".kb/conversations/x.json")).toBe(true);
  });
  it("allows normal paths", () => {
    expect(isReadOnlyPath("系统/戒律.md")).toBe(false);
  });
});
```

`docStorage.test.ts`:

```typescript
import { describe, expect, it, beforeEach } from "vitest";
import { getStoredEditMode, setStoredEditMode } from "./docStorage";

describe("docStorage", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("defaults to preview", () => {
    expect(getStoredEditMode()).toBe("preview");
  });

  it("persists markdown mode", () => {
    setStoredEditMode("markdown");
    expect(getStoredEditMode()).toBe("markdown");
  });
});
```

- [ ] **Step 2: 实现并改 import**

`types/doc.ts`:

```typescript
export type DocWidth = "narrow" | "wide";
export type DocMode = "panel" | "float" | "page";
export type EditMode = "preview" | "markdown";
export type UnsavedPrompt = "view" | "close" | "navigate" | "reload";
```

`docReadOnly.ts` / `docStorage.ts`：从 DocViewer 剪切 `isReadOnlyPath`、`getStoredEditMode`、`setStoredEditMode`（`EDIT_MODE_KEY` 放 docStorage）。

- [ ] **Step 3: 测试 + build 通过**

```bash
cd frontend && npm run test && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/doc.ts frontend/src/utils/docReadOnly.ts frontend/src/utils/docStorage.ts frontend/src/utils/*.test.ts frontend/src/components/DocViewer.tsx frontend/src/App.tsx
git commit -m "refactor(doc): extract doc types and pure utils with tests"
```

---

# Phase 1：拆分 Chat

## Task 3: `useChatScroll` — 滚动粘底

**Files:**
- Create: `frontend/src/hooks/chat/useChatScroll.ts`
- Create: `frontend/src/hooks/chat/useChatScroll.test.ts`
- Modify: `frontend/src/components/Chat.tsx`

- [ ] **Step 1: 写失败测试**

```typescript
import { renderHook, act } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useChatScroll } from "./useChatScroll";

describe("useChatScroll", () => {
  it("exposes stickToBottom ref default true", () => {
    const { result } = renderHook(() => useChatScroll());
    expect(result.current.stickToBottomRef.current).toBe(true);
  });
});
```

- [ ] **Step 2: 实现 hook（从 Chat 剪切 `isNearBottom`、`scrollMessagesToBottom`、scroll listener、layoutEffect）**

```typescript
import { useEffect, useLayoutEffect, useRef } from "react";

const SCROLL_BOTTOM_THRESHOLD = 80;

function isNearBottom(container: HTMLElement): boolean {
  const distance =
    container.scrollHeight - container.scrollTop - container.clientHeight;
  return distance <= SCROLL_BOTTOM_THRESHOLD;
}

export function useChatScroll(deps: unknown[] = []) {
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);

  function scrollMessagesToBottom() {
    const el = messagesContainerRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }

  useEffect(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const handleScroll = () => {
      stickToBottomRef.current = isNearBottom(el);
    };
    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  useLayoutEffect(() => {
    if (stickToBottomRef.current) scrollMessagesToBottom();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { messagesContainerRef, stickToBottomRef, scrollMessagesToBottom };
}
```

- [ ] **Step 3: Chat.tsx 改用 hook，`useChatScroll` 的 deps 传入 `[msgs, loadingHistory, streaming]`**

- [ ] **Step 4: test + build + 冒烟 #1 #7**

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(chat): extract useChatScroll hook"
```

---

## Task 4: `useChatConversation` — 历史加载

**Files:**
- Create: `frontend/src/hooks/chat/useChatConversation.ts`
- Modify: `frontend/src/components/Chat.tsx`

- [ ] **Step 1: 从 Chat 剪切 `conversationId` effect（含 `skipLoadRef` / `streamingRef` 守卫）**

Hook 签名：

```typescript
type Options = {
  conversationId: string | null;
  skipLoadRef: React.MutableRefObject<string | null>;
  streamingRef: React.MutableRefObject<boolean>;
};

export function useChatConversation({
  conversationId,
  skipLoadRef,
  streamingRef,
}: Options) {
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [summarized, setSummarized] = useState(false);
  const [summaryPath, setSummaryPath] = useState<string | null>(null);
  // ... effect 原样搬入
  return {
    msgs,
    setMsgs,
    loadingHistory,
    summarized,
    setSummarized,
    summaryPath,
    setSummaryPath,
  };
}
```

- [ ] **Step 2: Chat.tsx 删除重复 state/effect，调用 hook**

- [ ] **Step 3: build + 冒烟 #1（切换对话加载历史）**

- [ ] **Step 4: Commit**

---

## Task 5: `useAgentStream` — 流式核心（最高风险，单独 PR）

**Files:**
- Create: `frontend/src/hooks/chat/useAgentStream.ts`
- Modify: `frontend/src/components/Chat.tsx`

**注意:** 保留 `patchAssistant` 写最后一项的注释与实现；`streamingAssistantIdxRef` 仅用于 UI `isLiveStreaming` 判断，留在 Chat 或一并传入 hook。

- [ ] **Step 1: 写表征测试（mock `chatStream`）**

`useAgentStream.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAgentStream } from "./useAgentStream";
import * as api from "../../api";

vi.mock("../../api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../../api")>();
  return {
    ...mod,
    chatStream: vi.fn(),
    createConversation: vi.fn().mockResolvedValue({ id: "new-cid" }),
  };
});

describe("useAgentStream", () => {
  beforeEach(() => {
    vi.mocked(api.chatStream).mockImplementation(async function* () {
      yield { event: "done", data: { sources: [] } };
    });
  });

  it("sets streaming false after completion", async () => {
    const setMsgs = vi.fn((updater) =>
      typeof updater === "function" ? updater([]) : updater,
    );
    const { result } = renderHook(() =>
      useAgentStream({
        conversationId: "cid-1",
        previewPath: null,
        webEnabled: false,
        msgs: [],
        setMsgs,
        onSidebarRefresh: vi.fn(),
        conversationIdRef: { current: "cid-1" },
        skipLoadRef: { current: null },
        streamingRef: { current: false },
        stickToBottomRef: { current: true },
      }),
    );

    await act(async () => {
      await result.current.runAgentStream("hello");
    });

    expect(result.current.streaming).toBe(false);
  });
});
```

- [ ] **Step 2: 实现 hook — 原样搬移 `runAgentStream`、`ensureConversationId` 逻辑**

导出：

```typescript
export function useAgentStream(options: UseAgentStreamOptions) {
  const [streaming, setStreaming] = useState(false);
  const [liveElapsedMs, setLiveElapsedMs] = useState(0);
  const streamingStartRef = useRef<number | null>(null);
  const streamingAssistantIdxRef = useRef<number | null>(null);
  // ... streaming timer effect
  // ... runAgentStream, ensureConversationId
  return {
    streaming,
    liveElapsedMs,
    streamingAssistantIdxRef,
    streamingRef,
    runAgentStream,
    ensureConversationId,
  };
}
```

- [ ] **Step 3: Chat.tsx 仅保留 UI 编排**

- [ ] **Step 4: test + build + 完整冒烟 #1 #2 #7**

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(chat): extract useAgentStream hook with characterization test"
```

---

## Task 6: Chat 子组件 — MessageList + InputBar

**Files:**
- Create: `frontend/src/components/chat/ChatMessageRow.tsx`
- Create: `frontend/src/components/chat/ChatMessageList.tsx`
- Create: `frontend/src/components/chat/ChatInputBar.tsx`
- Modify: `frontend/src/components/Chat.tsx`

- [ ] **Step 1: 剪切 `renderMessageMeta`、`renderMessageContent`、`messageHasBody` 到 `ChatMessageRow.tsx`**

Props 显式列出（不要 spread 整个 Chat state）：

```typescript
export type ChatMessageRowProps = {
  message: ChatMessage;
  index: number;
  isLiveStreaming: boolean;
  liveElapsedMs: number;
  previewPath?: string | null;
  conversationId: string | null;
  onOpenSource: (src: SourceRef) => void;
  onQuestionResolved: (
    blockId: string,
    result: IngestResult,
    choiceLabel: string,
  ) => void;
};
```

- [ ] **Step 2: `ChatMessageList.tsx` 负责 `msgs.map` + loading/empty 态**

- [ ] **Step 3: `ChatInputBar.tsx` 收拢 textarea、附件、联网、发送、沉淀按钮；`adjustInputHeight` 留在此组件**

- [ ] **Step 4: Chat.tsx 目标形态（示意，约 120–150 行）**

```typescript
export function Chat(props: Props) {
  const conversationIdRef = useRef(props.conversationId);
  // hooks: useChatConversation, useChatScroll, useAgentStream
  // handlers: send, archive, onFile, handleQuestionResolved, handleOpenSource
  return (
    <div className="chat-panel">
      <ChatMessageList ... />
      {streaming && <StreamingBar liveElapsedMs={liveElapsedMs} />}
      <ChatInputBar ... />
    </div>
  );
}
```

- [ ] **Step 5: build + 冒烟清单全部 Chat 相关项**

- [ ] **Step 6: Commit**

```bash
git commit -m "refactor(chat): split MessageList and InputBar components"
```

**Phase 1 完成标准:** `Chat.tsx` ≤ 200 行；`npm run test && npm run build` 绿；冒烟 1/2/7 通过。

---

# Phase 2：拆分 DocViewer

## Task 7: `useDocLoader` — 加载与 refresh 世代

**Files:**
- Create: `frontend/src/hooks/doc/useDocLoader.ts`
- Modify: `frontend/src/components/DocViewer.tsx`

- [ ] **Step 1: 搬移 `loadDoc`、`loadGenRef`、`lastRefreshKeyRef`、`doc/body/savedBody/loading/error` state**

Hook 返回：

```typescript
export function useDocLoader(path: string, refreshKey: number) {
  // ...
  return {
    doc,
    body,
    setBody,
    savedBody,
    setSavedBody,
    loading,
    error,
    loadedPath,
    loadDoc,
    loadGenRef,
    userEditedRef,
    previewRemountKey,
    bumpPreviewRemount: () => setPreviewRemountKey((k) => k + 1),
  };
}
```

- [ ] **Step 2: path/refreshKey effect 暂留 DocViewer（下一步与 dirty 合并）**

- [ ] **Step 3: build + 冒烟 #3 #4**

- [ ] **Step 4: Commit**

---

## Task 8: `useDocDirtyPrompt` — 未保存状态机（最高风险）

**Files:**
- Create: `frontend/src/hooks/doc/useDocDirtyPrompt.ts`
- Create: `frontend/src/hooks/doc/useDocDirtyPrompt.test.ts`
- Modify: `frontend/src/components/DocViewer.tsx`

- [ ] **Step 1: 写失败测试（纯逻辑部分）**

把 `resolveUnsavedPromptAfterAction` 的核心分支抽成可测函数 `resolveUnsavedAction(prompt, action)` 或在 hook 外导出 `applyUnsavedResolution`：

```typescript
import { describe, expect, it } from "vitest";
import { nextUnsavedAfterDiscard } from "./useDocDirtyPrompt";

describe("nextUnsavedAfterDiscard", () => {
  it("close prompt clears and signals finishClose", () => {
    expect(nextUnsavedAfterDiscard("close")).toEqual({ kind: "finishClose" });
  });
  it("navigate prompt signals completeNavigation", () => {
    expect(nextUnsavedAfterDiscard("navigate")).toEqual({
      kind: "completeNavigation",
    });
  });
});
```

- [ ] **Step 2: 搬移以下到 hook（**原样**）：**

`dirty` 计算、`unsavedPrompt` state、`pendingNavRef`、`handleSave`、`handleConfirmSave/Discard`、`handleClose`、`onBindClose` effect、`completePendingNavigation`、`applyDiscard`

- [ ] **Step 3: path/refresh effect 移入 hook，接收 `onNavigationBlocked`**

- [ ] **Step 4: test + build + 冒烟 #4 #7（未保存全路径）**

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(doc): extract useDocDirtyPrompt state machine"
```

---

## Task 9: `useDocHighlight` + `DocMergeReviewBar`

**Files:**
- Create: `frontend/src/hooks/doc/useDocHighlight.ts`
- Create: `frontend/src/components/doc/DocMergeReviewBar.tsx`
- Modify: `frontend/src/components/DocViewer.tsx`

- [ ] **Step 1: 高亮 effect（TreeWalker）移入 `useDocHighlight(bodyRef, highlightText, loading, doc, editMode)`**

- [ ] **Step 2: footer 合并审阅 JSX + `ensureMergeActionConfirmed` + `runMergeAction` 移入 `DocMergeReviewBar.tsx`**

- [ ] **Step 3: build + 冒烟 #5**

- [ ] **Step 4: Commit**

---

## Task 10: `DocViewerHeader` + `DocViewerBody`

**Files:**
- Create: `frontend/src/components/doc/DocViewerHeader.tsx`
- Create: `frontend/src/components/doc/DocViewerBody.tsx`
- Modify: `frontend/src/components/DocViewer.tsx`

- [ ] **Step 1: Header 含 title、toolbar、mode toggle、outline、layout buttons**

- [ ] **Step 2: Body 含 meta bar、preview/markdown/merge textarea 三分支**

- [ ] **Step 3: DocViewer 变薄：组合 hooks + 子组件 + `DocDiffModal`**

目标：

```typescript
export function DocViewer(props: Props) {
  const loader = useDocLoader(props.path, props.refreshKey ?? 0);
  const dirty = useDocDirtyPrompt({ ...props, ...loader });
  useDocHighlight({ ... });
  const outline = useDocOutline(...); // 可内联或小型 hook

  return (
    <div className={...}>
      <DocViewerHeader ... />
      <DocViewerBody ... />
      {props.mergeReview && <DocMergeReviewBar ... />}
      <DocDiffModal ... />
    </div>
  );
}
```

- [ ] **Step 4: build + 冒烟 #3 #4 #5 #7**

- [ ] **Step 5: Commit**

**Phase 2 完成标准:** `DocViewer.tsx` ≤ 200 行；测试绿；冒烟 3–5、7 通过。

---

# Phase 3：拆分 App

## Task 11: `useMergeReviewSession` + `useKbFileSelection`

**Files:**
- Create: `frontend/src/hooks/app/useMergeReviewSession.ts`
- Create: `frontend/src/hooks/app/useKbFileSelection.ts`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: `useMergeReviewSession` 封装**

State: `mergeReview`, `mergeSourceQuestion`  
Effects: `previewPath` → `getActiveMerge`  
Handlers: `handleMergeAccept/Regenerate/Reject`, `handleMergeComplete`

```typescript
export function useMergeReviewSession(options: {
  previewPath: string | null;
  openDocPreview: (path: string, excerpt?: string, opts?: { pin?: boolean }) => void;
  closeDocPreview: () => void;
  refreshKb: (changedPath?: string) => void;
  setDocRefreshKey: React.Dispatch<React.SetStateAction<number>>;
}) {
  // ...
}
```

- [ ] **Step 2: `useKbFileSelection` 封装 `selectionMode`、`selectedPaths`、`handleToggleSelect`（含 shift 范围）、`handleSelectFolderAll`、`docs`**

- [ ] **Step 3: App.tsx 删除对应 state/handlers**

- [ ] **Step 4: build + 冒烟 #5 #6**

- [ ] **Step 5: Commit**

---

## Task 12: `DocPreviewContext` — 消除 prop 钻孔

**Files:**
- Create: `frontend/src/contexts/DocPreviewContext.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Chat.tsx`（改为 `useDocPreview()` 可选）

- [ ] **Step 1: Context 值**

```typescript
export type DocPreviewContextValue = {
  previewPath: string | null;
  openDoc: (path: string, excerpt?: string, options?: { pin?: boolean }) => void;
  closeDoc: () => void;
  refreshKb: (changedPath?: string) => void;
};

export function DocPreviewProvider({ children, value }: {
  children: React.ReactNode;
  value: DocPreviewContextValue;
}) { ... }

export function useDocPreview(): DocPreviewContextValue {
  const ctx = useContext(DocPreviewContext);
  if (!ctx) throw new Error("useDocPreview outside provider");
  return ctx;
}
```

- [ ] **Step 2: App 包裹 `<DocPreviewProvider>`**

- [ ] **Step 3: Chat Props 精简 — `previewPath`/`onOpenDoc`/`onKbChanged` 改从 context 读取（**保留 props 作为 override 一层 release**，先 context 内部用，props 仍传以保持兼容，下一步删 props）**

- [ ] **Step 4: build + 冒烟**

- [ ] **Step 5: Commit**

---

## Task 13: App 布局子组件

**Files:**
- Create: `frontend/src/components/app/AppShell.tsx`
- Create: `frontend/src/components/app/DocFloatLayer.tsx`
- Create: `frontend/src/components/app/DocPinnedPanel.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: `DocFloatLayer` — backdrop + float `DocViewer`（float 模式 props 列表固定）**

- [ ] **Step 2: `DocPinnedPanel` — aside + panel `DocViewer`**

- [ ] **Step 3: `AppShell` — shell className 计算、`Sidebar`、main、`SearchSnippetModal`、`MergeSourceQuestion`**

- [ ] **Step 4: `App.tsx` 仅组合 hooks + provider + AppShell（目标 ≤ 120 行）**

示意：

```typescript
export default function App() {
  const docPreview = useDocPreviewState(); // pin/focus/width/close ref
  const merge = useMergeReviewSession({ ...docPreview });
  const selection = useKbFileSelection();
  const conversation = useConversationShell();

  return (
    <DocPreviewProvider value={docPreview.contextValue}>
      <AppShell
        sidebar={<Sidebar ... />}
        chat={<Chat conversationId={conversation.activeId} ... />}
        docFloat={docPreview.showFloat ? <DocFloatLayer ... /> : null}
        docPinned={docPreview.showPinned ? <DocPinnedPanel ... /> : null}
        modals={...}
      />
    </DocPreviewProvider>
  );
}
```

- [ ] **Step 5: 删除 Chat 已冗余 props（`onOpenDoc` 等）**

- [ ] **Step 6: 全量冒烟清单 1–7**

- [ ] **Step 7: Commit**

```bash
git commit -m "refactor(app): split layout components and DocPreviewContext"
```

**Phase 3 完成标准:** `App.tsx` ≤ 150 行；全冒烟通过；`npm run test && npm run build` 绿。

---

## Task 14: 收尾 — 导出边界与文档

**Files:**
- Modify: `frontend/src/components/Chat.tsx`（确保无 default 重复导出）
- Optional: `frontend/src/hooks/index.ts` barrel（**仅当 import 路径混乱时**）

- [ ] **Step 1: 跑 `npm run lint`，修新增 warning**

- [ ] **Step 2: 统计行数确认达标**

```bash
# PowerShell
@( "Chat.tsx", "DocViewer.tsx", "App.tsx" ) | ForEach-Object {
  $n = (Get-Content "frontend/src/components/$_" -ErrorAction SilentlyContinue).Count
  if (-not $n) { $n = (Get-Content "frontend/src/$_").Count }
  "$_ : $n"
}
```

- [ ] **Step 3: 在计划文末勾选完成，不另写 README**

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 流式 patch 写错消息索引 | Task 5 表征测试 + 手动冒烟首问/继续对话 |
| dirty 状态机回归 | Task 8 单测 + 四条未保存路径手工测 |
| StrictMode 双 mount 覆盖流式 | 保留 `skipLoadRef`/`streamingRef`，禁止「优化掉」 |
| Context 引发隐式依赖 | Task 12 分两步：先并存 props，再删 props |
| 合并审阅 race | `useMergeReviewSession` 保留 `cancelled` flag，不改动 |

---

## 不建议做的事（YAGNI）

- 不引入 Zustand/Redux
- 不顺便改 CSS 类名或视觉
- 不拆 `Sidebar.tsx`（本轮范围外）
- 不为 `DocLivePreview`（Milkdown）写单元测试（太重）；靠冒烟
- 不做路由级 code splitting（与本轮无关）

---

## 预估工作量

| Phase | 任务数 | 预估 | 建议 PR |
|-------|--------|------|---------|
| 0 安全网 | 3 | 0.5 天 | PR-1 |
| 1 Chat | 4 | 1–1.5 天 | PR-2 |
| 2 DocViewer | 4 | 1.5–2 天 | PR-3 |
| 3 App | 4 | 1 天 | PR-4 |

合计约 **4–5 天**专注开发（含冒烟），比一次性重写安全一个数量级。

---

## 执行选项

**Plan complete.** 推荐执行方式：

1. **Subagent-Driven（推荐）** — 每 Task 派生子 agent，Task 5/8 后强制人工冒烟
2. **Inline Execution** — 本会话用 executing-plans 按 Phase 批量执行，Phase 边界人工确认

**从哪开始？** 建议独立 worktree（`using-git-worktrees`）上从 **Task 0** 开始。
