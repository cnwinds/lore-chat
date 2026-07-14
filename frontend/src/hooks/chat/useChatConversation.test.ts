import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useChatConversation } from "./useChatConversation";
import * as api from "../../api";

vi.mock("../../api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../../api")>();
  return {
    ...mod,
    getConversation: vi.fn(),
  };
});

describe("useChatConversation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not overwrite optimistic messages while streaming when history load completes", async () => {
    let resolveLoad: ((value: Awaited<ReturnType<typeof api.getConversation>>) => void) | undefined;
    vi.mocked(api.getConversation).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveLoad = resolve;
        }),
    );

    const skipLoadRef = { current: null as string | null };
    const streamingRef = { current: false };

    const { result } = renderHook(() =>
      useChatConversation({
        conversationId: "cid-1",
        skipLoadRef,
        streamingRef,
      }),
    );

    await waitFor(() => {
      expect(api.getConversation).toHaveBeenCalled();
    });

    streamingRef.current = true;
    result.current.setMsgs([
      { role: "user", text: "hello", ts: "2026-01-01T00:00:00.000Z" },
      { role: "assistant", timeline: [], ts: "2026-01-01T00:00:01.000Z" },
    ]);

    resolveLoad?.({
      id: "cid-1",
      title: "t",
      created_at: "",
      updated_at: "",
      message_count: 0,
      summarized: false,
      summary_path: null,
      messages: [],
    });

    await waitFor(() => {
      expect(result.current.loadingHistory).toBe(false);
    });

    expect(result.current.msgs).toHaveLength(2);
    expect(result.current.msgs[0]).toMatchObject({ role: "user", text: "hello" });
  });
});
