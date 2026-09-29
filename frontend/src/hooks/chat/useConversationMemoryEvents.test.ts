import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import {
  memoryEventLabel,
  useConversationMemoryEvents,
} from "./useConversationMemoryEvents";
import * as api from "../../api";

vi.mock("../../api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../../api")>();
  return {
    ...mod,
    getConversationEvents: vi.fn(),
  };
});

describe("memoryEventLabel", () => {
  it("maps memory event types to UI labels", () => {
    expect(memoryEventLabel("memory_updated")).toBe("已更新记忆");
    expect(memoryEventLabel("memory_decayed")).toBe("记忆已衰减");
    expect(memoryEventLabel("cards_updated")).toBe("已更新知识卡");
    expect(memoryEventLabel("other")).toBeNull();
  });
});

describe("useConversationMemoryEvents", () => {
  let unmountHook: (() => void) | undefined;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    unmountHook?.();
    unmountHook = undefined;
    vi.useRealTimers();
  });

  it("primes cursor without showing historical events, then surfaces new memory events", async () => {
    vi.mocked(api.getConversationEvents)
      .mockResolvedValueOnce({
        events: [
          {
            id: "e1",
            event_type: "memory_updated",
            payload: { type: "memory_updated" },
            created_at: "2026-01-01T00:00:00.000Z",
          },
        ],
      })
      .mockResolvedValueOnce({
        events: [
          {
            id: "e2",
            event_type: "memory_decayed",
            payload: { type: "memory_decayed" },
            created_at: "2026-01-01T00:00:05.000Z",
          },
        ],
      });

    const hook = renderHook(() =>
      useConversationMemoryEvents("cid-1", { pollMs: 20 }),
    );
    unmountHook = hook.unmount;
    const { result } = hook;

    await waitFor(() => {
      expect(api.getConversationEvents).toHaveBeenCalledTimes(1);
    });
    expect(result.current.notice).toBeNull();

    await waitFor(
      () => {
        expect(result.current.notice).toEqual({
          id: "e2",
          kind: "memory_decayed",
          label: "记忆已衰减",
        });
      },
      { timeout: 2000 },
    );
    expect(api.getConversationEvents).toHaveBeenNthCalledWith(2, "cid-1", {
      afterEventId: "e1",
    });
  });

  it("surfaces cards_updated events with the expected label", async () => {
    vi.mocked(api.getConversationEvents)
      .mockResolvedValueOnce({
        events: [
          {
            id: "e0",
            event_type: "memory_updated",
            payload: { type: "memory_updated" },
            created_at: "2026-01-01T00:00:00.000Z",
          },
        ],
      })
      .mockResolvedValueOnce({
        events: [
          {
            id: "e-cards",
            event_type: "cards_updated",
            payload: { type: "cards_updated" },
            created_at: "2026-01-01T00:00:10.000Z",
          },
        ],
      });

    const hook = renderHook(() =>
      useConversationMemoryEvents("cid-1", { pollMs: 20 }),
    );
    unmountHook = hook.unmount;
    const { result } = hook;

    await waitFor(() => {
      expect(api.getConversationEvents).toHaveBeenCalledTimes(1);
    });
    expect(result.current.notice).toBeNull();

    await waitFor(
      () => {
        expect(result.current.notice).toEqual({
          id: "e-cards",
          kind: "cards_updated",
          label: "已更新知识卡",
        });
      },
      { timeout: 2000 },
    );
  });

  it("clears notice when conversation changes", async () => {
    vi.mocked(api.getConversationEvents).mockResolvedValue({ events: [] });

    const hook = renderHook(
      ({ cid }: { cid: string | null }) =>
        useConversationMemoryEvents(cid, { pollMs: 20 }),
      { initialProps: { cid: "cid-1" as string | null } },
    );
    unmountHook = hook.unmount;
    const { result, rerender } = hook;

    await waitFor(() => {
      expect(api.getConversationEvents).toHaveBeenCalled();
    });

    act(() => {
      result.current.dismissNotice();
    });

    rerender({ cid: null });
    expect(result.current.notice).toBeNull();
  });
});
