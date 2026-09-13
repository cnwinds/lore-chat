import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GroupList } from "./GroupList";

vi.mock("../../api", () => ({
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
      },
    ],
  })),
}));

afterEach(() => {
  cleanup();
});

describe("GroupList", () => {
  it("lists groups and highlights the active one", async () => {
    const onSelect = vi.fn();
    render(
      <GroupList
        activeGroupId="bbbbbbbbbbbb"
        onSelectGroup={onSelect}
        onNewGroup={vi.fn()}
      />,
    );
    expect(await screen.findByText("登录页")).toBeTruthy();
    expect(screen.getByText("通用助手大师、游戏开发助手")).toBeTruthy();
    expect(document.querySelector(".group-avatar--2")).toBeTruthy();
    screen.getByText("登录页").click();
    expect(onSelect).toHaveBeenCalledWith(
      "bbbbbbbbbbbb",
      expect.objectContaining({ id: "bbbbbbbbbbbb", title: "登录页" }),
    );
  });
});
