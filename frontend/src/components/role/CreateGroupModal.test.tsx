import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CreateGroupModal } from "./CreateGroupModal";
import type { RoleSummary } from "../../api";

afterEach(() => {
  cleanup();
});

const roles: RoleSummary[] = [
  {
    id: "default",
    name: "通用助手大师",
    avatar: null,
    system_prompt: "",
    is_default: true,
    sort_order: 0,
    created_at: "",
    updated_at: "",
  },
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

describe("CreateGroupModal", () => {
  it("requires two roles before submit", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <CreateGroupModal open roles={roles} onClose={vi.fn()} onConfirm={onConfirm} />,
    );
    expect(screen.getByRole("button", { name: "发起群聊" })).toBeDisabled();
    await user.click(screen.getByRole("option", { name: /通用助手大师/ }));
    await user.click(screen.getByRole("option", { name: /游戏开发助手/ }));
    await user.click(screen.getByRole("button", { name: "发起群聊" }));
    expect(onConfirm).toHaveBeenCalledWith(
      "通用助手大师、游戏开发助手",
      ["default", "game"],
      "",
    );
  });
});
