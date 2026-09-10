import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import {
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
});
