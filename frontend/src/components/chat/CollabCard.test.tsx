import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getRoomStatus } from "../../api";
import { CollabCard } from "./CollabCard";

const defaultStatus = {
  id: "aaaaaaaaaaaa",
  kind: "peer_dm",
  state: "working",
  preview: "正在改登录页",
  queued_count: 0,
  pending_questions: [],
  participant_role_ids: [] as string[],
};

afterEach(() => {
  cleanup();
  vi.mocked(getRoomStatus).mockReset();
  vi.mocked(getRoomStatus).mockResolvedValue(defaultStatus);
});

vi.mock("../../api", () => ({
  getRoomStatus: vi.fn(async () => defaultStatus),
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

  it("lists in-progress group assignments", async () => {
    vi.mocked(getRoomStatus).mockResolvedValue({
      id: "aaaaaaaaaaaa",
      kind: "group",
      state: "done",
      preview: "已派给同学",
      queued_count: 0,
      pending_questions: [],
      participant_role_ids: [],
      assignments: [
        {
          id: "asg1",
          assigner_role_id: "a",
          assigner_name: "通用助手",
          assignee_role_id: "b",
          assignee_name: "游戏开发助手",
          status: "working",
          due_at: "2026-09-14T12:00:00+08:00",
          brief: "改登录页",
        },
        {
          id: "asg2",
          assigner_role_id: "a",
          assigner_name: "通用助手",
          assignee_role_id: "c",
          assignee_name: "研究员",
          status: "overdue",
          due_at: "2026-09-14T11:00:00+08:00",
          brief: "写文案",
        },
      ],
    });
    render(
      <CollabCard
        block={{
          type: "tool",
          id: "t2",
          tool: "send_message",
          label: "发给其他角色",
          ts: "t",
          status: "done",
          summary: "已发送。协作房间 conversation://aaaaaaaaaaaa",
          room_id: "aaaaaaaaaaaa",
          target_role_name: "游戏开发助手",
          wake_status: "queued",
        }}
      />,
    );
    expect(await screen.findByText("游戏开发助手 · 进行中")).toBeTruthy();
    expect(await screen.findByText("研究员 · 已超时")).toBeTruthy();
  });
});
