import { createRef } from "react";
import { describe, expect, it } from "vitest";
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
});
