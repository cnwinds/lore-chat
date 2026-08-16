import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useChatConversation } from "./useChatConversation";
import { createStreamOwnership } from "./streamOwnership";
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
    const streamOwnership = createStreamOwnership();

    const { result } = renderHook(() =>
      useChatConversation({
        conversationId: "cid-1",
        skipLoadRef,
        streamOwnership,
      }),
    );

    await waitFor(() => {
      expect(api.getConversation).toHaveBeenCalled();
    });

    streamOwnership.streamingRef.current = true;
    result.current.setMsgs([
      { role: "user", text: "hello", ts: "2026-01-01T00:00:00.000Z" },
      { role: "assistant", timeline: [], ts: "2026-01-01T00:00:01.000Z" },
    ]);
    streamOwnership.streamConversationIdRef.current = "cid-1";
    streamOwnership.msgsConversationIdRef.current = "cid-1";

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

  it("loads the new conversation even when another conversation is still streaming", async () => {
    vi.mocked(api.getConversation).mockImplementation(async (cid: string) => ({
      id: cid,
      title: cid,
      created_at: "",
      updated_at: "",
      message_count: 1,
      summarized: false,
      summary_path: null,
      messages: [
        {
          role: "user",
          text: `msg-${cid}`,
          ts: "2026-01-01T00:00:00.000Z",
        },
      ],
    }));

    const skipLoadRef = { current: null as string | null };
    const streamOwnership = createStreamOwnership();
    streamOwnership.streamingRef.current = true;
    streamOwnership.streamConversationIdRef.current = "cid-a";
    streamOwnership.msgsConversationIdRef.current = "cid-a";

    const { result, rerender } = renderHook(
      ({ conversationId }) =>
        useChatConversation({
          conversationId,
          skipLoadRef,
          streamOwnership,
        }),
      { initialProps: { conversationId: "cid-a" } },
    );

    result.current.setMsgs([
      { role: "user", text: "from-a", ts: "2026-01-01T00:00:00.000Z" },
      { role: "assistant", timeline: [], ts: "2026-01-01T00:00:01.000Z" },
    ]);

    rerender({ conversationId: "cid-b" });

    await waitFor(() => {
      expect(result.current.msgs).toEqual([
        expect.objectContaining({ role: "user", text: "msg-cid-b" }),
      ]);
    });
    expect(api.getConversation).toHaveBeenCalledWith("cid-b");
    expect(streamOwnership.msgsConversationIdRef.current).toBe("cid-b");
  });

  it("reloads when switching back to a streaming conversation whose msgs belong elsewhere", async () => {
    vi.mocked(api.getConversation).mockImplementation(async (cid: string) => ({
      id: cid,
      title: cid,
      created_at: "",
      updated_at: "",
      message_count: 1,
      summarized: false,
      summary_path: null,
      messages: [
        {
          role: "user",
          text: `msg-${cid}`,
          ts: "2026-01-01T00:00:00.000Z",
        },
      ],
    }));

    const skipLoadRef = { current: null as string | null };
    const streamOwnership = createStreamOwnership();
    streamOwnership.streamingRef.current = true;
    streamOwnership.streamConversationIdRef.current = "cid-a";

    const { result, rerender } = renderHook(
      ({ conversationId }) =>
        useChatConversation({
          conversationId,
          skipLoadRef,
          streamOwnership,
        }),
      { initialProps: { conversationId: "cid-a" } },
    );

    result.current.setMsgs([
      { role: "user", text: "from-a", ts: "2026-01-01T00:00:00.000Z" },
    ]);
    streamOwnership.msgsConversationIdRef.current = "cid-a";

    rerender({ conversationId: "cid-b" });
    await waitFor(() => {
      expect(result.current.msgs[0]).toMatchObject({ text: "msg-cid-b" });
    });

    // Still streaming A, but msgs now belong to B — switching back must reload A.
    rerender({ conversationId: "cid-a" });
    await waitFor(() => {
      expect(result.current.msgs).toEqual([
        expect.objectContaining({ role: "user", text: "msg-cid-a" }),
      ]);
    });
  });
});
