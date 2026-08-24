import { describe, expect, it, vi } from "vitest";
import { scrollKbTreeNodeIntoView } from "./kbTreeScroll";

describe("scrollKbTreeNodeIntoView", () => {
  it("scrolls when node is outside the tree scroll viewport", () => {
    const scrollRoot = document.createElement("div");
    scrollRoot.className = "sidebar-tree-scroll";
    const el = document.createElement("div");
    scrollRoot.appendChild(el);
    document.body.appendChild(scrollRoot);

    scrollRoot.getBoundingClientRect = () =>
      ({ top: 0, bottom: 200, left: 0, right: 100, width: 100, height: 200 }) as DOMRect;
    el.getBoundingClientRect = () =>
      ({ top: 250, bottom: 290, left: 0, right: 100, width: 100, height: 40 }) as DOMRect;

    const scrollIntoView = vi.fn();
    el.scrollIntoView = scrollIntoView;

    scrollKbTreeNodeIntoView(el);
    expect(scrollIntoView).toHaveBeenCalledWith({
      block: "nearest",
      behavior: "smooth",
    });

    scrollRoot.remove();
  });

  it("does not scroll when node is already fully visible", () => {
    const scrollRoot = document.createElement("div");
    scrollRoot.className = "sidebar-tree-scroll";
    const el = document.createElement("div");
    scrollRoot.appendChild(el);
    document.body.appendChild(scrollRoot);

    scrollRoot.getBoundingClientRect = () =>
      ({ top: 0, bottom: 400, left: 0, right: 100, width: 100, height: 400 }) as DOMRect;
    el.getBoundingClientRect = () =>
      ({ top: 40, bottom: 80, left: 0, right: 100, width: 100, height: 40 }) as DOMRect;

    const scrollIntoView = vi.fn();
    el.scrollIntoView = scrollIntoView;

    scrollKbTreeNodeIntoView(el);
    expect(scrollIntoView).not.toHaveBeenCalled();

    scrollRoot.remove();
  });
});
