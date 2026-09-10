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
    getConversationMessages: vi.fn(),
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

  it("clears foreign messages immediately when switching conversations", async () => {
    let resolveB: ((value: Awaited<ReturnType<typeof api.getConversation>>) => void) | undefined;
    vi.mocked(api.getConversation).mockImplementation(async (cid: string) => {
      if (cid === "cid-a") {
        return {
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
              text: "msg-a",
              ts: "2026-01-01T00:00:00.000Z",
            },
          ],
        };
      }
      return new Promise((resolve) => {
        resolveB = resolve;
      });
    });

    const skipLoadRef = { current: null as string | null };
    const streamOwnership = createStreamOwnership();
    const { result, rerender } = renderHook(
      ({ conversationId }) =>
        useChatConversation({
          conversationId,
          skipLoadRef,
          streamOwnership,
        }),
      { initialProps: { conversationId: "cid-a" } },
    );

    await waitFor(() => {
      expect(result.current.msgs[0]).toMatchObject({ text: "msg-a" });
    });

    rerender({ conversationId: "cid-b" });
    await waitFor(() => {
      expect(result.current.msgs).toEqual([]);
    });
    expect(streamOwnership.msgsConversationIdRef.current).toBeNull();

    resolveB?.({
      id: "cid-b",
      title: "cid-b",
      created_at: "",
      updated_at: "",
      message_count: 1,
      summarized: false,
      summary_path: null,
      messages: [
        {
          role: "user",
          text: "msg-b",
          ts: "2026-01-01T00:00:00.000Z",
        },
      ],
    });
    await waitFor(() => {
      expect(result.current.msgs[0]).toMatchObject({ text: "msg-b" });
    });
  });

  it("loads only a tail when messageTail is set", async () => {
    vi.mocked(api.getConversation).mockResolvedValue({
      id: "cid-1",
      title: "t",
      created_at: "",
      updated_at: "",
      message_count: 20,
      summarized: false,
      summary_path: null,
      older_message_count: 12,
      messages: [
        { id: "m-tail", role: "user", text: "recent", ts: "2026-01-01T00:00:00.000Z" },
      ],
    });

    const skipLoadRef = { current: null as string | null };
    const streamOwnership = createStreamOwnership();
    const { result } = renderHook(() =>
      useChatConversation({
        conversationId: "cid-1",
        skipLoadRef,
        streamOwnership,
        messageTail: 8,
      }),
    );

    await waitFor(() => {
      expect(result.current.msgs[0]).toMatchObject({ text: "recent" });
    });
    expect(api.getConversation).toHaveBeenCalledWith("cid-1", { tail: 8 });
    expect(result.current.olderMessageCount).toBe(12);
  });

  it("loads the full conversation when jumping to a message", async () => {
    vi.mocked(api.getConversation).mockResolvedValue({
      id: "cid-1",
      title: "t",
      created_at: "",
      updated_at: "",
      message_count: 2,
      summarized: false,
      summary_path: null,
      older_message_count: 0,
      messages: [
        { id: "hit", role: "user", text: "found", ts: "2026-01-01T00:00:00.000Z" },
      ],
    });

    const skipLoadRef = { current: null as string | null };
    const streamOwnership = createStreamOwnership();
    renderHook(() =>
      useChatConversation({
        conversationId: "cid-1",
        skipLoadRef,
        streamOwnership,
        messageTail: 8,
        pendingJump: { conversationId: "cid-1", messageId: "hit" },
      }),
    );

    await waitFor(() => {
      expect(api.getConversation).toHaveBeenCalledWith("cid-1");
    });
    expect(api.getConversation).not.toHaveBeenCalledWith("cid-1", { tail: 8 });
  });

  it("does not paint a conversation that belongs to another role", async () => {
    vi.mocked(api.getConversation).mockResolvedValue({
      id: "cid-other",
      title: "t",
      created_at: "",
      updated_at: "",
      message_count: 1,
      role_id: "role-b",
      summarized: false,
      summary_path: null,
      messages: [
        {
          role: "user",
          text: "other-role-msg",
          ts: "2026-01-01T00:00:00.000Z",
        },
      ],
    });

    const skipLoadRef = { current: null as string | null };
    const streamOwnership = createStreamOwnership();
    const onRoleMismatch = vi.fn();
    const { result } = renderHook(() =>
      useChatConversation({
        conversationId: "cid-other",
        roleId: "default",
        skipLoadRef,
        streamOwnership,
        onRoleMismatch,
      }),
    );

    await waitFor(() => {
      expect(result.current.loadingHistory).toBe(false);
    });
    expect(result.current.msgs).toEqual([]);
    expect(onRoleMismatch).toHaveBeenCalledWith("cid-other", "default");
  });

  it("treats a missing role_id as the default role", async () => {
    vi.mocked(api.getConversation).mockResolvedValue({
      id: "cid-legacy",
      title: "t",
      created_at: "",
      updated_at: "",
      message_count: 1,
      summarized: false,
      summary_path: null,
      messages: [
        {
          role: "user",
          text: "legacy-default",
          ts: "2026-01-01T00:00:00.000Z",
        },
      ],
    });

    const skipLoadRef = { current: null as string | null };
    const streamOwnership = createStreamOwnership();
    const onRoleMismatch = vi.fn();
    const { result } = renderHook(() =>
      useChatConversation({
        conversationId: "cid-legacy",
        roleId: "default",
        skipLoadRef,
        streamOwnership,
        onRoleMismatch,
      }),
    );

    await waitFor(() => {
      expect(result.current.msgs[0]).toMatchObject({ text: "legacy-default" });
    });
    expect(onRoleMismatch).not.toHaveBeenCalled();
  });
});
