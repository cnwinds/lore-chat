import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatMessageList } from "./ChatMessageList";

const emptyRefs = {
  streamingAssistantIdxRef: { current: null },
  messagesContainerRef: createRef<HTMLDivElement>(),
  messagesEndRef: createRef<HTMLDivElement>(),
};

describe("ChatMessageList loading chrome", () => {
  it("keeps the centered wordmark while history is loading", () => {
    render(
      <ChatMessageList
        msgs={[]}
        loadingHistory
        streaming={false}
        liveElapsedMs={0}
        streamingAssistantIdxRef={emptyRefs.streamingAssistantIdxRef}
        messagesContainerRef={emptyRefs.messagesContainerRef}
        messagesEndRef={emptyRefs.messagesEndRef}
        conversationId="cid"
        timelineHasMore
        onOpenSource={() => {}}
        onQuestionResolved={() => {}}
      />,
    );

    expect(screen.getByText("加载对话中…")).toBeInTheDocument();
    expect(document.querySelector(".chat-welcome")).not.toBeNull();
    expect(document.querySelector(".chat-messages-inner--fill")).not.toBeNull();
    expect(document.querySelector(".chat-empty")).toBeNull();
    expect(screen.queryByText("向上滚动加载更早对话")).toBeNull();
  });

  it("shows welcome headline and suggestion chips only when a picker is provided", () => {
    const onSuggestionPick = vi.fn();
    const { rerender } = render(
      <ChatMessageList
        msgs={[]}
        loadingHistory={false}
        streaming={false}
        liveElapsedMs={0}
        streamingAssistantIdxRef={emptyRefs.streamingAssistantIdxRef}
        messagesContainerRef={emptyRefs.messagesContainerRef}
        messagesEndRef={emptyRefs.messagesEndRef}
        conversationId="cid"
        onOpenSource={() => {}}
        onQuestionResolved={() => {}}
        onSuggestionPick={onSuggestionPick}
      />,
    );

    expect(screen.getByText("把对话，沉淀成知识库")).toBeInTheDocument();
    const chips = Array.from(
      document.querySelectorAll<HTMLButtonElement>(".chat-welcome-suggestion"),
    );
    expect(chips.length).toBeGreaterThanOrEqual(3);
    chips[0].click();
    expect(onSuggestionPick).toHaveBeenCalledWith(chips[0].textContent);

    // 只读转录没有输入框，不渲染建议
    rerender(
      <ChatMessageList
        msgs={[]}
        loadingHistory={false}
        streaming={false}
        liveElapsedMs={0}
        streamingAssistantIdxRef={emptyRefs.streamingAssistantIdxRef}
        messagesContainerRef={emptyRefs.messagesContainerRef}
        messagesEndRef={emptyRefs.messagesEndRef}
        conversationId="cid"
        onOpenSource={() => {}}
        onQuestionResolved={() => {}}
      />,
    );
    expect(screen.queryByText("把对话，沉淀成知识库")).toBeInTheDocument();
    expect(
      document.querySelector(".chat-welcome-suggestions"),
    ).toBeNull();
  });

  it("marks a search-jump gap so the unread middle is not implied to be loaded", () => {
    render(
      <ChatMessageList
        msgs={[
          {
            id: "tip-1",
            role: "user",
            text: "刚才",
            ts: "2026-09-01T00:00:00.000Z",
          },
        ]}
        historicalSegments={[
          {
            conversationId: "old",
            title: "很早",
            createdAt: "2025-01-01T00:00:00.000Z",
            messages: [
              {
                id: "hit",
                role: "user",
                text: "很早以前",
                ts: "2025-01-01T00:00:00.000Z",
              },
            ],
            isTip: false,
            olderMessageCount: 0,
            jumped: true,
          },
        ]}
        loadingHistory={false}
        streaming={false}
        liveElapsedMs={0}
        streamingAssistantIdxRef={emptyRefs.streamingAssistantIdxRef}
        messagesContainerRef={emptyRefs.messagesContainerRef}
        messagesEndRef={emptyRefs.messagesEndRef}
        conversationId="tip"
        onOpenSource={() => {}}
        onQuestionResolved={() => {}}
      />,
    );

    expect(screen.getByText("定位到搜索结果 · 中间消息未加载")).toBeInTheDocument();
    expect(document.querySelector('[data-jumped="true"]')).not.toBeNull();
  });

  it("rebuilds the session outline after historical messages load", () => {
    render(
      <ChatMessageList
        msgs={[
          {
            id: "tip-1",
            role: "user",
            text: "刚才",
          },
        ]}
        historicalSegments={[
          {
            conversationId: "old",
            title: "很早",
            createdAt: "2025-01-01T00:00:00.000Z",
            messages: [
              { id: "h1", role: "user", text: "第一问" },
              { id: "h2", role: "user", text: "第二问" },
            ],
            isTip: false,
            olderMessageCount: 0,
          },
        ]}
        loadingHistory={false}
        streaming={false}
        liveElapsedMs={0}
        streamingAssistantIdxRef={emptyRefs.streamingAssistantIdxRef}
        messagesContainerRef={emptyRefs.messagesContainerRef}
        messagesEndRef={emptyRefs.messagesEndRef}
        conversationId="tip"
        onOpenSource={() => {}}
        onQuestionResolved={() => {}}
      />,
    );

    expect(
      screen.getByRole("button", { name: /会话导航（3 条提问）/ }),
    ).toBeInTheDocument();
  });

  it("renders a group participation card instead of group transcript", () => {
    render(
      <ChatMessageList
        msgs={[
          {
            id: "tip-1",
            role: "user",
            text: "刚才",
            ts: "2026-09-01T00:00:00.000Z",
          },
        ]}
        historicalSegments={[
          {
            conversationId: "g1",
            title: "登录页协作",
            createdAt: "2026-01-01T00:00:00.000Z",
            messages: [],
            isTip: false,
            olderMessageCount: 0,
            kind: "group_card",
            excerpt: "登录页已接上真实接口",
            cardStatus: "done",
          },
        ]}
        loadingHistory={false}
        streaming={false}
        liveElapsedMs={0}
        streamingAssistantIdxRef={emptyRefs.streamingAssistantIdxRef}
        messagesContainerRef={emptyRefs.messagesContainerRef}
        messagesEndRef={emptyRefs.messagesEndRef}
        conversationId="tip"
        onOpenSource={() => {}}
        onQuestionResolved={() => {}}
      />,
    );

    expect(screen.getByText("登录页协作")).toBeInTheDocument();
    expect(screen.getByText("登录页已接上真实接口")).toBeInTheDocument();
    expect(screen.queryByText("群全文")).toBeNull();
    expect(document.querySelector(".room-interject")).toBeNull();
  });
});
