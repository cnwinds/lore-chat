import { describe, expect, it, vi } from "vitest";
import { planSearchJump, scrollToMessageHighlight } from "./useConversationJump";

describe("scrollToMessageHighlight", () => {
  it("scrolls to data-message-id and applies highlight class", () => {
    const el = document.createElement("div");
    el.dataset.messageId = "m1";
    document.body.appendChild(el);
    const scrollIntoView = vi.fn();
    el.scrollIntoView = scrollIntoView;
    scrollToMessageHighlight("m1", { start: 0, end: 2 });
    expect(scrollIntoView).toHaveBeenCalled();
    document.body.removeChild(el);
  });
});


describe("planSearchJump", () => {
  const jump = { conversationId: "old", messageId: "hit" };

  it("waits while history is still loading", () => {
    expect(
      planSearchJump({
        pendingJump: jump,
        msgs: [],
        historicalSegments: [],
        loading: true,
        revealAttempted: false,
      }),
    ).toBe("wait");
  });

  it("scrolls when the hit is already in the current tail", () => {
    expect(
      planSearchJump({
        pendingJump: jump,
        msgs: [{ id: "hit" }],
        historicalSegments: [],
        loading: false,
        revealAttempted: false,
      }),
    ).toBe("scroll");
  });

  it("scrolls when the hit is already in a historical segment", () => {
    expect(
      planSearchJump({
        pendingJump: jump,
        msgs: [{ id: "tip" }],
        historicalSegments: [{ messages: [{ id: "hit" }] }],
        loading: false,
        revealAttempted: false,
      }),
    ).toBe("scroll");
  });

  it("reveals an around-window once when the hit is nowhere in memory", () => {
    expect(
      planSearchJump({
        pendingJump: jump,
        msgs: [{ id: "tip" }],
        historicalSegments: [],
        loading: false,
        revealAttempted: false,
      }),
    ).toBe("reveal");
  });

  it("settles after a failed reveal instead of walking older pages", () => {
    expect(
      planSearchJump({
        pendingJump: jump,
        msgs: [{ id: "tip" }],
        historicalSegments: [],
        loading: false,
        revealAttempted: true,
      }),
    ).toBe("settle");
  });
});
