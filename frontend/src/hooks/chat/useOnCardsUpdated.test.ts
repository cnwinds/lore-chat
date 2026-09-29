import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MemoryEventNotice } from "./useConversationMemoryEvents";
import { useOnCardsUpdated } from "./useOnCardsUpdated";

const cardsNotice = (id: string): MemoryEventNotice => ({
  id,
  kind: "cards_updated",
  label: "已更新知识卡",
});

describe("useOnCardsUpdated", () => {
  it("invokes callback once per notice even when callback identity changes on rerender", () => {
    const first = vi.fn();
    const second = vi.fn();
    const notice = cardsNotice("n1");

    const { rerender } = renderHook(
      ({ cb }: { cb: () => void }) => useOnCardsUpdated(notice, cb),
      { initialProps: { cb: first } },
    );

    expect(first).toHaveBeenCalledTimes(1);
    expect(second).not.toHaveBeenCalled();

    rerender({ cb: second });
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).not.toHaveBeenCalled();
  });

  it("invokes callback again when a new cards_updated notice id arrives", () => {
    const cb = vi.fn();

    const { rerender } = renderHook(
      ({ notice }: { notice: MemoryEventNotice }) =>
        useOnCardsUpdated(notice, cb),
      { initialProps: { notice: cardsNotice("n1") } },
    );
    expect(cb).toHaveBeenCalledTimes(1);

    rerender({ notice: cardsNotice("n2") });
    expect(cb).toHaveBeenCalledTimes(2);
  });

  it("does not invoke callback for non-cards_updated notices", () => {
    const cb = vi.fn();
    const notice: MemoryEventNotice = {
      id: "n1",
      kind: "memory_updated",
      label: "已更新记忆",
    };

    renderHook(() => useOnCardsUpdated(notice, cb));
    expect(cb).not.toHaveBeenCalled();
  });
});
