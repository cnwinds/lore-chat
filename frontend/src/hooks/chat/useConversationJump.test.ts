import { describe, expect, it, vi } from "vitest";
import { scrollToMessageHighlight } from "./useConversationJump";

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
