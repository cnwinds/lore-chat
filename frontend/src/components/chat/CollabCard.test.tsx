import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CollabCard } from "./CollabCard";

afterEach(() => {
  cleanup();
});

vi.mock("../../api", () => ({
  getRoomStatus: vi.fn(async () => ({
    id: "aaaaaaaaaaaa",
    kind: "peer_dm",
    state: "working",
    preview: "正在改登录页",
    queued_count: 0,
    pending_questions: [],
    participant_role_ids: [],
  })),
}));

describe("CollabCard", () => {
  it("renders target, status and jump button", async () => {
    const onOpen = vi.fn();
    render(
      <CollabCard
        block={{
          type: "tool",
          id: "t1",
          tool: "send_message",
          label: "发给其他角色",
          ts: "t",
          status: "done",
          summary: "已发送。协作房间 conversation://aaaaaaaaaaaa",
          room_id: "aaaaaaaaaaaa",
          target_role_name: "游戏开发助手",
          wake_status: "started",
        }}
        onOpenConversation={onOpen}
      />,
    );
    expect(screen.getByText(/协作 · 游戏开发助手/)).toBeTruthy();
    expect(screen.queryByText(/conversation:\/\//)).toBeNull();
    expect(screen.getByText(/已发送/)).toBeTruthy();
    const jump = screen.getByRole("button", { name: "查看协作" });
    jump.click();
    expect(onOpen).toHaveBeenCalledWith({ conversationId: "aaaaaaaaaaaa" });
  });
});
