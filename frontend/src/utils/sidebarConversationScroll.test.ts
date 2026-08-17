import { describe, expect, it, vi } from "vitest";
import { scrollConversationItemIntoView } from "./sidebarConversationScroll";

describe("scrollConversationItemIntoView", () => {
  it("scrolls when item is outside the list viewport", () => {
    const list = document.createElement("div");
    list.className = "conversation-list";
    const el = document.createElement("div");
    list.appendChild(el);
    document.body.appendChild(list);

    list.getBoundingClientRect = () =>
      ({ top: 0, bottom: 200, left: 0, right: 100, width: 100, height: 200 }) as DOMRect;
    el.getBoundingClientRect = () =>
      ({ top: 250, bottom: 290, left: 0, right: 100, width: 100, height: 40 }) as DOMRect;

    const scrollIntoView = vi.fn();
    el.scrollIntoView = scrollIntoView;

    scrollConversationItemIntoView(el);
    expect(scrollIntoView).toHaveBeenCalledWith({
      block: "nearest",
      behavior: "smooth",
    });

    list.remove();
  });

  it("does not scroll when item is already fully visible under sticky pad", () => {
    const list = document.createElement("div");
    list.className = "conversation-list";
    const el = document.createElement("div");
    list.appendChild(el);
    document.body.appendChild(list);

    list.getBoundingClientRect = () =>
      ({ top: 0, bottom: 400, left: 0, right: 100, width: 100, height: 400 }) as DOMRect;
    el.getBoundingClientRect = () =>
      ({ top: 40, bottom: 80, left: 0, right: 100, width: 100, height: 40 }) as DOMRect;

    const scrollIntoView = vi.fn();
    el.scrollIntoView = scrollIntoView;

    scrollConversationItemIntoView(el);
    expect(scrollIntoView).not.toHaveBeenCalled();

    list.remove();
  });
});
