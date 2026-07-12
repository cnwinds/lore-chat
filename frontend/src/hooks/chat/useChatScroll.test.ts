import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useChatScroll } from "./useChatScroll";

describe("useChatScroll", () => {
  it("exposes stickToBottom ref default true", () => {
    const { result } = renderHook(() => useChatScroll());
    expect(result.current.stickToBottomRef.current).toBe(true);
  });
});
