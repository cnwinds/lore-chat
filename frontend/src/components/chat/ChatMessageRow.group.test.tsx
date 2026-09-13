import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ChatMessageRow } from "./ChatMessageRow";
import type { ChatMessage, RoleSummary } from "../../api";

afterEach(() => {
  cleanup();
});

const roles: RoleSummary[] = [
  {
    id: "game",
    name: "游戏开发助手",
    avatar: null,
    system_prompt: "",
    is_default: false,
    sort_order: 1,
    created_at: "",
    updated_at: "",
  },
];

const baseProps = {
  isLiveStreaming: false,
  liveElapsedMs: 0,
  previewPath: null,
  conversationId: "g1",
  onOpenSource: () => {},
  onQuestionResolved: () => {},
  layout: "group" as const,
  roles,
};

describe("ChatMessageRow group layout", () => {
  it("shows a role name and avatar, not a 来自 tag", () => {
    const message: ChatMessage = {
      id: "m1",
      role: "assistant",
      text: "登录页改好了",
      speaker_kind: "role",
      speaker_id: "game",
      speaker_name: "游戏开发助手",
      ts: "2026-01-01T00:00:00.000Z",
    };
    render(<ChatMessageRow message={message} {...baseProps} />);
    expect(screen.getByText("游戏开发助手")).toBeTruthy();
    expect(screen.getByText("登录页改好了")).toBeTruthy();
    expect(screen.queryByText(/来自/)).toBeNull();
    expect(document.querySelector(".chat-row-group-role")).toBeTruthy();
    const row = document.querySelector(".chat-row-group-role");
    expect(row?.firstElementChild?.classList.contains("role-avatar")).toBe(
      true,
    );
    expect(row?.querySelector(".chat-row-group-name")?.textContent).toBe(
      "游戏开发助手",
    );
  });

  it("keeps the owner on the right", () => {
    const message: ChatMessage = {
      id: "m2",
      role: "user",
      text: "@游戏开发助手 改登录页",
      speaker_kind: "user",
      speaker_name: "主人",
      ts: "2026-01-01T00:00:00.000Z",
    };
    render(<ChatMessageRow message={message} {...baseProps} />);
    expect(document.querySelector(".chat-row-group-owner")).toBeTruthy();
    expect(screen.queryByText("主人")).toBeNull();
  });
});
