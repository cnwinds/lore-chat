import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CollapsibleUserText,
  userMessageCollapsedMaxHeight,
  userMessageTextOverflows,
} from "./CollapsibleUserText";

function mockLineHeight(px: number) {
  vi.spyOn(window, "getComputedStyle").mockReturnValue({
    lineHeight: `${px}px`,
    getPropertyValue: (prop: string) => (prop === "line-height" ? `${px}px` : ""),
  } as CSSStyleDeclaration);
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("userMessageTextOverflows", () => {
  it("detects when scroll height exceeds six lines", () => {
    expect(userMessageTextOverflows(200, 20)).toBe(true);
    expect(userMessageTextOverflows(120, 20)).toBe(false);
    expect(userMessageCollapsedMaxHeight(20)).toBe(120);
  });
});

describe("CollapsibleUserText", () => {
  it("does not show toggle for short messages", () => {
    mockLineHeight(20);
    vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(40);
    render(<CollapsibleUserText text="短消息" />);
    expect(screen.queryByRole("button", { name: /展开全文/ })).toBeNull();
  });

  it("collapses long messages and expands on click", () => {
    mockLineHeight(20);
    vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(280);
    const text = Array.from({ length: 12 }, (_, i) => `第 ${i + 1} 行`).join("\n");
    const { container } = render(<CollapsibleUserText text={text} />);

    const toggle = screen.getByRole("button", { name: /展开全文/ });
    expect(container.querySelector(".chat-user-text-wrap--collapsed")).toBeTruthy();
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: /收起/ })).toBeTruthy();
    expect(container.querySelector(".chat-user-text-wrap--collapsed")).toBeNull();
  });
});
