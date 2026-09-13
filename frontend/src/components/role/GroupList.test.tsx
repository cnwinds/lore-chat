import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RoleList } from "./RoleList";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    listRoles: vi.fn(async () => ({
      roles: [
        {
          id: "default",
          name: "通用助手大师",
          avatar: null,
          system_prompt: "",
          is_default: true,
          sort_order: 0,
          created_at: "2026-08-01T10:00:00+08:00",
          updated_at: "2026-08-01T10:00:00+08:00",
          last_active_at: "2026-08-01T10:00:00+08:00",
        },
      ],
    })),
    listRooms: vi.fn(async () => ({
      rooms: [
        {
          id: "bbbbbbbbbbbb",
          title: "登录页",
          kind: "group",
          participant_role_ids: ["a", "b"],
          participant_names: ["通用助手大师", "游戏开发助手"],
          participants: [
            { id: "a", name: "通用助手大师" },
            { id: "b", name: "游戏开发助手" },
          ],
          last_active_at: "2026-08-08T12:00:00+08:00",
          last_reply_preview: "先改登录页",
        },
      ],
    })),
    searchConversations: vi.fn(async () => ({ hits: [] })),
  };
});

afterEach(() => {
  cleanup();
});

describe("RoleList inbox", () => {
  it("mixes groups into the chat list without a separate heading", async () => {
    const onSelect = vi.fn();
    render(
      <RoleList
        activeRoleId="default"
        activeGroupId="bbbbbbbbbbbb"
        onSelectRole={vi.fn()}
        onSelectGroup={onSelect}
        onNewRole={vi.fn()}
        onNewGroup={vi.fn()}
      />,
    );
    expect(await screen.findByText("登录页")).toBeTruthy();
    expect(screen.getByText("先改登录页")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "群聊" })).toBeNull();
    expect(document.querySelector(".group-avatar-mark")).toBeTruthy();
    expect(document.querySelector(".group-avatar--2")).toBeTruthy();
    const names = (await screen.findAllByText(/登录页|通用助手大师/)).map(
      (el) => el.textContent,
    );
    expect(names[0]).toBe("登录页");
    screen.getByText("登录页").click();
    expect(onSelect).toHaveBeenCalledWith(
      "bbbbbbbbbbbb",
      expect.objectContaining({ id: "bbbbbbbbbbbb", title: "登录页" }),
    );
  });

  it("opens a compose menu with role and group actions", async () => {
    const user = userEvent.setup();
    const onNewGroup = vi.fn();
    render(
      <RoleList
        activeRoleId="default"
        onSelectRole={vi.fn()}
        onNewRole={vi.fn()}
        onNewGroup={onNewGroup}
      />,
    );
    await screen.findByText("登录页");
    await user.click(screen.getByLabelText("新建"));
    expect(screen.getByRole("menuitem", { name: "新角色" })).toBeTruthy();
    const groupItem = screen.getByRole("menuitem", { name: "发起群聊" });
    expect(groupItem).toBeDisabled();
  });
});
