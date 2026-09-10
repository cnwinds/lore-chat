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
});
