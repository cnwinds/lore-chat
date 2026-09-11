import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import {
  SEARCH_JUMP_RADIUS,
  TIMELINE_FIRST_PAGE_SIZE,
  TIMELINE_PAGE_SIZE,
  useRoleTimeline,
} from "./useRoleTimeline";
import * as api from "../../api";

vi.mock("../../api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../../api")>();
  return {
    ...mod,
    getRoleTimeline: vi.fn(),
    getConversation: vi.fn(),
    getConversationMessages: vi.fn(),
  };
});

describe("useRoleTimeline", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("first load asks for tip metadata only", async () => {
    vi.mocked(api.getRoleTimeline).mockResolvedValue({
      role_id: "r1",
      tip_conversation_id: "tip",
      continuity_idle_hours: 6,
      has_more: true,
      segments: [
        {
          id: "tip",
          title: "新对话",
          created_at: "2026-01-02T00:00:00Z",
          updated_at: "2026-01-02T00:00:00Z",
          message_count: 0,
        },
      ],
    });

    const { result } = renderHook(() =>
      useRoleTimeline({
        roleId: "r1",
        tipConversationId: "tip",
        messageLimit: 8,
      }),
    );

    await waitFor(() => {
      expect(result.current.hasMore).toBe(true);
    });
    expect(api.getRoleTimeline).toHaveBeenCalledWith("r1", {
      includeMessages: false,
      limit: TIMELINE_FIRST_PAGE_SIZE,
    });
    expect(result.current.historicalSegments).toEqual([]);
  });

  it("loadOlder fetches one truncated historical segment", async () => {
    vi.mocked(api.getRoleTimeline)
      .mockResolvedValueOnce({
        role_id: "r1",
        tip_conversation_id: "tip",
        continuity_idle_hours: 6,
        has_more: true,
        segments: [
          {
            id: "tip",
            title: "新对话",
            created_at: "2026-01-02T00:00:00Z",
            updated_at: "2026-01-02T00:00:00Z",
            message_count: 0,
          },
        ],
      })
      .mockResolvedValueOnce({
        role_id: "r1",
        tip_conversation_id: "tip",
        continuity_idle_hours: 6,
        has_more: false,
        segments: [
          {
            id: "old",
            title: "旧段",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
            message_count: 20,
            older_message_count: 12,
            messages: [
              {
                id: "m1",
                role: "assistant",
                text: "tail",
                ts: "2026-01-01T00:00:00Z",
              },
            ],
          },
        ],
      });

    const { result } = renderHook(() =>
      useRoleTimeline({
        roleId: "r1",
        tipConversationId: "tip",
        messageLimit: 8,
      }),
    );

    await waitFor(() => {
      expect(result.current.hasMore).toBe(true);
    });

    await act(async () => {
      await result.current.loadOlder();
    });

    expect(api.getRoleTimeline).toHaveBeenLastCalledWith("r1", {
      limit: TIMELINE_PAGE_SIZE,
      messageLimit: 8,
      beforeCreatedAt: "2026-01-02T00:00:00Z",
      beforeId: "tip",
    });
    expect(result.current.historicalSegments).toHaveLength(1);
    expect(result.current.historicalSegments[0]).toMatchObject({
      conversationId: "old",
      olderMessageCount: 12,
    });
  });

  it("loadOlder prepends earlier messages in the oldest segment first", async () => {
    vi.mocked(api.getRoleTimeline)
      .mockResolvedValueOnce({
        role_id: "r1",
        tip_conversation_id: "tip",
        continuity_idle_hours: 6,
        has_more: true,
        segments: [
          {
            id: "tip",
            title: "新对话",
            created_at: "2026-01-02T00:00:00Z",
            updated_at: "2026-01-02T00:00:00Z",
            message_count: 0,
          },
        ],
      })
      .mockResolvedValueOnce({
        role_id: "r1",
        tip_conversation_id: "tip",
        continuity_idle_hours: 6,
        has_more: false,
        segments: [
          {
            id: "old",
            title: "旧段",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
            message_count: 4,
            older_message_count: 2,
            messages: [
              {
                id: "m2",
                role: "user",
                text: "later",
                ts: "2026-01-01T00:00:02Z",
              },
            ],
          },
        ],
      });
    vi.mocked(api.getConversationMessages).mockResolvedValue({
      older_message_count: 0,
      messages: [
        {
          id: "m1",
          role: "user",
          text: "earlier",
          ts: "2026-01-01T00:00:01Z",
        },
      ],
    });

    const { result } = renderHook(() =>
      useRoleTimeline({
        roleId: "r1",
        tipConversationId: "tip",
        messageLimit: 8,
      }),
    );
    await waitFor(() => expect(result.current.hasMore).toBe(true));
    await act(async () => {
      await result.current.loadOlder();
    });
    await act(async () => {
      await result.current.loadOlder();
    });

    expect(api.getConversationMessages).toHaveBeenCalledWith("old", {
      beforeId: "m2",
      limit: 8,
    });
    expect(result.current.historicalSegments[0].messages.map((m) => m.id)).toEqual([
      "m1",
      "m2",
    ]);
    expect(result.current.historicalSegments[0].olderMessageCount).toBe(0);
  });

  it("switching role drops the previous role's segments", async () => {
    vi.mocked(api.getRoleTimeline)
      .mockResolvedValueOnce({
        role_id: "r1",
        tip_conversation_id: "tip",
        continuity_idle_hours: 6,
        has_more: true,
        segments: [
          {
            id: "tip",
            title: "新对话",
            created_at: "2026-01-02T00:00:00Z",
            updated_at: "2026-01-02T00:00:00Z",
            message_count: 0,
            role_id: "r1",
          },
        ],
      })
      .mockResolvedValueOnce({
        role_id: "r1",
        tip_conversation_id: "tip",
        continuity_idle_hours: 6,
        has_more: false,
        segments: [
          {
            id: "old",
            title: "旧段",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
            message_count: 1,
            role_id: "r1",
            messages: [
              {
                id: "m1",
                role: "assistant",
                text: "other-role",
                ts: "2026-01-01T00:00:00Z",
              },
            ],
          },
        ],
      })
      .mockResolvedValue({
        role_id: "default",
        tip_conversation_id: "d-tip",
        continuity_idle_hours: 6,
        has_more: false,
        segments: [
          {
            id: "d-tip",
            title: "新对话",
            created_at: "2026-01-03T00:00:00Z",
            updated_at: "2026-01-03T00:00:00Z",
            message_count: 0,
            role_id: "default",
          },
        ],
      });

    const { result, rerender } = renderHook(
      ({ roleId, tip }) =>
        useRoleTimeline({
          roleId,
          tipConversationId: tip,
          messageLimit: 8,
        }),
      { initialProps: { roleId: "r1", tip: "tip" } },
    );
    await waitFor(() => expect(result.current.hasMore).toBe(true));
    await act(async () => {
      await result.current.loadOlder();
    });
    expect(result.current.historicalSegments).toHaveLength(1);
    expect(result.current.historicalSegments[0].conversationId).toBe("old");

    rerender({ roleId: "default", tip: "d-tip" });
    await waitFor(() => {
      expect(result.current.historicalSegments).toEqual([]);
    });
  });

  it("loadOlder after a role switch uses the new role tip, not the previous conversation", async () => {
    vi.mocked(api.getRoleTimeline)
      .mockResolvedValueOnce({
        role_id: "r1",
        tip_conversation_id: "old-tip",
        continuity_idle_hours: 6,
        has_more: true,
        segments: [
          {
            id: "old-tip",
            title: "旧角色 tip",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
            message_count: 0,
            role_id: "r1",
          },
        ],
      })
      .mockResolvedValueOnce({
        role_id: "default",
        tip_conversation_id: "d-tip",
        continuity_idle_hours: 6,
        has_more: true,
        segments: [
          {
            id: "d-tip",
            title: "通用 tip",
            created_at: "2026-01-10T00:00:00Z",
            updated_at: "2026-01-10T00:00:00Z",
            message_count: 0,
            role_id: "default",
          },
        ],
      })
      .mockResolvedValueOnce({
        role_id: "default",
        tip_conversation_id: "d-tip",
        continuity_idle_hours: 6,
        has_more: false,
        segments: [
          {
            id: "d-old",
            title: "通用旧段",
            created_at: "2026-01-09T00:00:00Z",
            updated_at: "2026-01-09T00:00:00Z",
            message_count: 1,
            role_id: "default",
            messages: [
              {
                id: "m-def",
                role: "assistant",
                text: "default-history",
                ts: "2026-01-09T00:00:00Z",
              },
            ],
          },
        ],
      });

    const { result, rerender } = renderHook(
      ({ roleId, tip }) =>
        useRoleTimeline({
          roleId,
          tipConversationId: tip,
          messageLimit: 8,
        }),
      { initialProps: { roleId: "r1", tip: "old-tip" } },
    );
    await waitFor(() => expect(result.current.hasMore).toBe(true));

    // 父组件还没把 tip 改过来：模拟切角色后 conversationId 仍是上一角色的会话
    rerender({ roleId: "default", tip: "old-tip" });
    await waitFor(() => {
      expect(api.getRoleTimeline).toHaveBeenCalledWith("default", {
        includeMessages: false,
        limit: TIMELINE_FIRST_PAGE_SIZE,
      });
    });
    await waitFor(() => expect(result.current.hasMore).toBe(true));

    await act(async () => {
      await result.current.loadOlder();
    });
    expect(api.getRoleTimeline).toHaveBeenLastCalledWith("default", {
      limit: TIMELINE_PAGE_SIZE,
      messageLimit: 8,
      beforeCreatedAt: "2026-01-10T00:00:00Z",
      beforeId: "d-tip",
    });
    expect(result.current.historicalSegments).toEqual([
      expect.objectContaining({ conversationId: "d-old" }),
    ]);
  });

  it("revealAround inserts a jumped window instead of walking older segments", async () => {
    vi.mocked(api.getRoleTimeline).mockResolvedValue({
      role_id: "r1",
      tip_conversation_id: "tip",
      continuity_idle_hours: 6,
      has_more: true,
      segments: [
        {
          id: "tip",
          title: "新对话",
          created_at: "2026-01-02T00:00:00Z",
          updated_at: "2026-01-02T00:00:00Z",
          message_count: 0,
          role_id: "r1",
        },
      ],
    });
    vi.mocked(api.getConversation).mockResolvedValue({
      id: "ancient",
      title: "很早以前",
      created_at: "2025-01-01T00:00:00Z",
      updated_at: "2025-01-01T00:00:00Z",
      message_count: 200,
      role_id: "r1",
      summarized: false,
      summary_path: null,
      older_message_count: 80,
      newer_message_count: 119,
      messages: [
        {
          id: "hit",
          role: "user",
          text: "found",
          ts: "2025-01-01T00:00:00Z",
        },
      ],
    });
    vi.mocked(api.getConversationMessages).mockResolvedValue({
      older_message_count: 72,
      messages: [
        {
          id: "earlier",
          role: "user",
          text: "before-hit",
          ts: "2024-12-31T00:00:00Z",
        },
      ],
    });

    const { result } = renderHook(() =>
      useRoleTimeline({
        roleId: "r1",
        tipConversationId: "tip",
        messageLimit: 8,
      }),
    );
    await waitFor(() => expect(result.current.hasMore).toBe(true));

    await act(async () => {
      await expect(result.current.revealAround("ancient", "hit")).resolves.toBe(
        true,
      );
    });

    expect(api.getConversation).toHaveBeenCalledWith("ancient", {
      aroundId: "hit",
      radius: SEARCH_JUMP_RADIUS,
    });
    expect(result.current.historicalSegments).toEqual([
      expect.objectContaining({
        conversationId: "ancient",
        jumped: true,
        olderMessageCount: 80,
        newerMessageCount: 119,
      }),
    ]);

    const timelineCalls = vi.mocked(api.getRoleTimeline).mock.calls.length;
    await act(async () => {
      await result.current.loadOlder();
    });
    expect(api.getConversationMessages).toHaveBeenCalledWith("ancient", {
      beforeId: "hit",
      limit: 8,
    });
    expect(vi.mocked(api.getRoleTimeline).mock.calls.length).toBe(timelineCalls);
    expect(result.current.historicalSegments[0].messages.map((m) => m.id)).toEqual(
      ["earlier", "hit"],
    );
  });

  it("keeps a jumped window even when it belongs to the current tip", async () => {
    vi.mocked(api.getRoleTimeline).mockResolvedValue({
      role_id: "r1",
      tip_conversation_id: "tip",
      continuity_idle_hours: 6,
      has_more: false,
      segments: [
        {
          id: "tip",
          title: "当前",
          created_at: "2026-01-02T00:00:00Z",
          updated_at: "2026-01-02T00:00:00Z",
          message_count: 40,
          role_id: "r1",
        },
      ],
    });
    vi.mocked(api.getConversation).mockResolvedValue({
      id: "tip",
      title: "当前",
      created_at: "2026-01-02T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
      message_count: 40,
      role_id: "r1",
      summarized: false,
      summary_path: null,
      older_message_count: 20,
      newer_message_count: 7,
      messages: [
        {
          id: "old-hit",
          role: "user",
          text: "years-ago",
          ts: "2026-01-01T00:00:00Z",
        },
      ],
    });

    const { result } = renderHook(() =>
      useRoleTimeline({
        roleId: "r1",
        tipConversationId: "tip",
        messageLimit: 8,
      }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.revealAround("tip", "old-hit");
    });

    expect(result.current.historicalSegments).toEqual([
      expect.objectContaining({
        conversationId: "tip",
        jumped: true,
        messages: [expect.objectContaining({ id: "old-hit" })],
      }),
    ]);
  });

  it("does not fetch earlier timeline pages after a jump window is exhausted", async () => {
    vi.mocked(api.getRoleTimeline).mockResolvedValue({
      role_id: "r1",
      tip_conversation_id: "tip",
      continuity_idle_hours: 6,
      has_more: true,
      segments: [
        {
          id: "tip",
          title: "新对话",
          created_at: "2026-01-02T00:00:00Z",
          updated_at: "2026-01-02T00:00:00Z",
          message_count: 0,
          role_id: "r1",
        },
      ],
    });
    vi.mocked(api.getConversation).mockResolvedValue({
      id: "ancient",
      title: "很早以前",
      created_at: "2025-01-01T00:00:00Z",
      updated_at: "2025-01-01T00:00:00Z",
      message_count: 3,
      role_id: "r1",
      summarized: false,
      summary_path: null,
      older_message_count: 0,
      newer_message_count: 0,
      messages: [
        {
          id: "hit",
          role: "user",
          text: "found",
          ts: "2025-01-01T00:00:00Z",
        },
      ],
    });

    const { result } = renderHook(() =>
      useRoleTimeline({
        roleId: "r1",
        tipConversationId: "tip",
        messageLimit: 8,
      }),
    );
    await waitFor(() => expect(result.current.hasMore).toBe(true));
    await act(async () => {
      await result.current.revealAround("ancient", "hit");
    });
    const timelineCalls = vi.mocked(api.getRoleTimeline).mock.calls.length;

    await act(async () => {
      await expect(result.current.loadOlder()).resolves.toBe(false);
    });
    expect(api.getConversationMessages).not.toHaveBeenCalled();
    expect(vi.mocked(api.getRoleTimeline).mock.calls.length).toBe(timelineCalls);
  });
});
