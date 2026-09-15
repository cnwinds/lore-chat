import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAppEscapeKey } from "./useAppEscapeKey";
import { useDocPreviewLayout } from "./useDocPreviewLayout";

function useDocWithEscape() {
  const doc = useDocPreviewLayout(vi.fn());
  useAppEscapeKey(doc, null, () => undefined);
  return doc;
}

function pressEscape() {
  window.dispatchEvent(
    new KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
  );
}

describe("useAppEscapeKey", () => {
  it("closes the channel float without closing a pinned document", () => {
    const { result } = renderHook(() => useDocWithEscape());

    act(() => {
      result.current.openDocPreview("notes/a.md", undefined, { pin: true });
      result.current.openChannelPanel();
    });
    expect(result.current.channelPanelOpen).toBe(true);
    expect(result.current.pinnedPath).toBe("notes/a.md");

    act(() => {
      pressEscape();
    });
    expect(result.current.channelPanelOpen).toBe(false);
    expect(result.current.pinnedPath).toBe("notes/a.md");
  });

  it("closes memory before pinned, matching the left-edge slot order", () => {
    const { result } = renderHook(() => useDocWithEscape());

    act(() => {
      result.current.openDocPreview("notes/a.md", undefined, { pin: true });
      result.current.openMemoryPanel();
    });

    act(() => {
      pressEscape();
    });
    expect(result.current.memoryPanelOpen).toBe(false);
    expect(result.current.pinnedPath).toBe("notes/a.md");
  });
});
