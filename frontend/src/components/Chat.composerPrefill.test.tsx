import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Chat } from "./Chat";

vi.mock("../contexts/DocPreviewContext", () => ({
  useDocPreview: () => ({
    previewPath: null,
    openDoc: vi.fn(),
    refreshKb: vi.fn(),
  }),
}));

vi.mock("../hooks/useKbNameConflictPrompt", () => ({
  useKbNameConflictPrompt: () => ({
    promptConflict: vi.fn(),
    conflictDialog: null,
  }),
}));

vi.mock("../hooks/chat/useChatChainMediaCaps", () => ({
  useChatChainMediaCaps: () => ({
    videoSupported: false,
    maxVideos: 0,
    imageSupported: true,
    maxImages: 4,
    videoWireData: false,
  }),
}));

vi.mock("../hooks/chat/useChatConversation", () => ({
  useChatConversation: () => ({
    msgs: [],
    setMsgs: vi.fn(),
    loadingHistory: false,
    loadingOlderMessages: false,
    olderMessageCount: 0,
    loadOlderMessages: vi.fn(),
    setSummarized: vi.fn(),
    setSummaryPath: vi.fn(),
    respondingRoleId: null,
  }),
}));

vi.mock("../hooks/chat/useChatScroll", () => ({
  useChatScroll: () => ({
    messagesContainerRef: { current: null },
    stickToBottomRef: { current: true },
    onScroll: vi.fn(),
  }),
}));

vi.mock("../hooks/chat/useAgentStream", () => ({
  useAgentStream: () => ({
    streamingForView: false,
    reconciling: false,
    networkReconnectNeeded: false,
    retryNetworkReconcile: vi.fn(),
    liveElapsedMs: 0,
    streamNowMs: 0,
    streamingAssistantIdxRef: { current: null },
  }),
}));

vi.mock("../hooks/chat/useConversationMemoryEvents", () => ({
  useConversationMemoryEvents: () => ({
    memoryNotice: null,
    dismissMemoryNotice: vi.fn(),
  }),
}));

vi.mock("../hooks/chat/useOnCardsUpdated", () => ({
  useOnCardsUpdated: vi.fn(),
}));

vi.mock("../hooks/chat/useSendQueue", () => ({
  useSendQueue: () => ({
    items: [],
    paused: false,
    updateItem: vi.fn(),
    setItemTiming: vi.fn(),
    guideItem: vi.fn(),
    removeItem: vi.fn(),
    moveItem: vi.fn(),
    setAllTiming: vi.fn(),
    setAllMerge: vi.fn(),
    clear: vi.fn(),
  }),
}));

vi.mock("../hooks/chat/useOutboundOrchestrator", () => ({
  useOutboundOrchestrator: () => ({
    handleSend: vi.fn(),
    handleContinue: vi.fn(),
    handleRetry: vi.fn(),
    handleSkipFailed: vi.fn(),
  }),
}));

vi.mock("../hooks/chat/useRoleTimeline", () => ({
  useRoleTimeline: () => ({
    historicalSegments: [],
    continuityIdleHours: null,
    loading: false,
    loadingOlder: false,
    hasMore: false,
    loadOlder: vi.fn(),
    revealAround: vi.fn(),
  }),
  TIMELINE_AUTOFILL_MAX: 10,
  TIMELINE_MESSAGE_TAIL_DESKTOP: 40,
  TIMELINE_MESSAGE_TAIL_MOBILE: 20,
}));

vi.mock("../hooks/chat/useMentionPicker", () => ({
  useMentionPicker: () => ({
    open: false,
    hits: [],
    mention: null,
    selectedIndex: 0,
    setSelectedIndex: vi.fn(),
    apply: vi.fn(),
  }),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Chat composerPrefill", () => {
  it("prefills the composer when nonce changes", async () => {
    const { rerender } = render(
      <Chat conversationId={null} composerPrefill={null} />,
    );
    rerender(
      <Chat
        conversationId={null}
        composerPrefill={{ text: "请把下面这些经验固化为一个 Skill", nonce: 1 }}
      />,
    );
    const textarea = await screen.findByPlaceholderText("输入消息…");
    expect(textarea).toHaveValue("请把下面这些经验固化为一个 Skill");
  });
});
