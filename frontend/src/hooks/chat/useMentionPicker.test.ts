import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { KeyboardEvent } from "react";
import { useMentionPicker } from "./useMentionPicker";

const candidates = [
  { id: "default", name: "通用助手大师", avatar: null },
  { id: "game", name: "游戏开发助手", avatar: null },
];

function key(
  name: string,
  extra: Partial<KeyboardEvent<HTMLTextAreaElement>> = {},
): KeyboardEvent<HTMLTextAreaElement> {
  return {
    key: name,
    shiftKey: false,
    preventDefault: vi.fn(),
    nativeEvent: { isComposing: false },
    ...extra,
  } as KeyboardEvent<HTMLTextAreaElement>;
}

describe("useMentionPicker", () => {
  it("opens on @ and inserts the selected member with keyboard", () => {
    const setInput = vi.fn();
    const setCaret = vi.fn();
    const textarea = document.createElement("textarea");
    const { result } = renderHook(() =>
      useMentionPicker({
        input: "请 @",
        caret: 3,
        setInput,
        setCaret,
        textareaRef: { current: textarea },
        candidates,
      }),
    );

    expect(result.current.open).toBe(true);
    expect(result.current.hits).toHaveLength(2);

    act(() => {
      expect(result.current.handleKeyDown(key("ArrowDown"))).toBe(true);
    });
    expect(result.current.selectedIndex).toBe(1);

    act(() => {
      expect(result.current.handleKeyDown(key("Enter"))).toBe(true);
    });
    expect(setInput).toHaveBeenCalledWith("请 @游戏开发助手 ");
    expect(setCaret).toHaveBeenCalledWith(10);
  });

  it("closes on Escape without sending", () => {
    const { result } = renderHook(() =>
      useMentionPicker({
        input: "@",
        caret: 1,
        setInput: vi.fn(),
        setCaret: vi.fn(),
        textareaRef: { current: null },
        candidates,
      }),
    );
    act(() => {
      expect(result.current.handleKeyDown(key("Escape"))).toBe(true);
    });
    expect(result.current.open).toBe(false);
  });
});
