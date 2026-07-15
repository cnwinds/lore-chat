import { describe, expect, it } from "vitest";
import { act, render, waitFor, cleanup } from "@testing-library/react";
import { ChatMessageRow } from "./ChatMessageRow";
import type { ChatMessage } from "../../api";

const baseProps = {
  isLiveStreaming: false,
  liveElapsedMs: 0,
  previewPath: null,
  conversationId: "c1",
  onOpenSource: () => {},
  onQuestionResolved: () => {},
};

describe("ChatMessageRow timeline highlight", () => {
  it("highlights range inside timeline text blocks", async () => {
    const message: ChatMessage = {
      id: "m1",
      role: "assistant",
      text: "HelloWorld",
      timeline: [
        { type: "text", content: "Hello", ts: "t" },
        {
          type: "tool",
          id: "tool-1",
          tool: "search_kb",
          label: "搜索",
          ts: "t",
          status: "done",
          summary: "done",
        },
        { type: "text", content: "World", ts: "t" },
      ],
    };

    const { container } = render(
      <ChatMessageRow message={message} {...baseProps} />,
    );
    const row = container.querySelector('[data-message-id="m1"]')!;

    await act(async () => {
      row.dispatchEvent(
        new CustomEvent("highlight-range", {
          detail: { start: 6, end: 10, offsetVersion: "unicode-codepoint-v1" },
          bubbles: true,
        }),
      );
    });

    await waitFor(() => {
      const mark = container.querySelector("mark.message-range-highlight");
      expect(mark).not.toBeNull();
      expect(mark?.textContent).toBe("orld");
    });
    cleanup();
  });

  it("skips highlight when offset version is unsupported", async () => {
    const message: ChatMessage = {
      id: "m2",
      role: "assistant",
      text: "Hello",
      timeline: [{ type: "text", content: "Hello", ts: "t" }],
    };

    const { container } = render(
      <ChatMessageRow message={message} {...baseProps} />,
    );
    const row = container.querySelector('[data-message-id="m2"]')!;

    await act(async () => {
      row.dispatchEvent(
        new CustomEvent("highlight-range", {
          detail: { start: 0, end: 5, offsetVersion: "utf16-v1" },
          bubbles: true,
        }),
      );
    });

    await waitFor(() => {
      expect(container.querySelector("mark.message-range-highlight")).toBeNull();
    });
    cleanup();
  });
});
