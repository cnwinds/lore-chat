import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getRoom, updateRoom, type RoleSummary, type RoomSummary } from "../../api";
import { GroupConfigPanel } from "./GroupConfigPanel";

afterEach(() => {
  cleanup();
});

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    getRoom: vi.fn(),
    updateRoom: vi.fn(),
  };
});

const roles: RoleSummary[] = [
  {
    id: "default",
    name: "通用",
    avatar: null,
    system_prompt: "",
    is_default: true,
    sort_order: 0,
    created_at: "",
    updated_at: "",
  },
  {
    id: "dev",
    name: "开发",
    avatar: null,
    system_prompt: "",
    is_default: false,
    sort_order: 1,
    created_at: "",
    updated_at: "",
  },
];

const room: RoomSummary = {
  id: "g1",
  title: "项目群",
  kind: "group",
  avatar: null,
  participant_role_ids: ["default", "dev"],
  participants: [
    { id: "default", name: "通用", avatar: null },
    { id: "dev", name: "开发", avatar: null },
  ],
};

describe("GroupConfigPanel", () => {
  it("hides when collapsed and shows members on the right rail", async () => {
    vi.mocked(getRoom).mockResolvedValue(room);
    const { rerender } = render(
      <GroupConfigPanel
        roomId="g1"
        roles={roles}
        collapsed
        onToggleCollapsed={vi.fn()}
      />,
    );
    expect(document.querySelector(".role-config-panel--collapsed")).toHaveAttribute(
      "hidden",
    );

    rerender(
      <GroupConfigPanel
        roomId="g1"
        roles={roles}
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    );
    expect(await screen.findByText("项目群")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "成员" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "收起群设置" })).toBeInTheDocument();
  });

  it("opens the editor from the gear and saves identity", async () => {
    const user = userEvent.setup();
    vi.mocked(getRoom).mockResolvedValue(room);
    vi.mocked(updateRoom).mockResolvedValue({ ...room, title: "新群名" });
    const onSaved = vi.fn();
    render(
      <GroupConfigPanel
        roomId="g1"
        roles={roles}
        collapsed={false}
        onToggleCollapsed={vi.fn()}
        onSaved={onSaved}
      />,
    );
    await screen.findByRole("heading", { name: "成员" });
    await user.click(screen.getByRole("button", { name: "群设置" }));
    const nameInput = screen.getByPlaceholderText("群名称");
    await user.clear(nameInput);
    await user.type(nameInput, "新群名");
    await user.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => {
      expect(updateRoom).toHaveBeenCalledWith(
        "g1",
        expect.objectContaining({ title: "新群名", role_ids: ["default", "dev"] }),
      );
    });
    expect(onSaved).toHaveBeenCalled();
  });

  it("enters edit mode when editRequestKey bumps", async () => {
    vi.mocked(getRoom).mockResolvedValue(room);
    const { rerender } = render(
      <GroupConfigPanel
        roomId="g1"
        roles={roles}
        collapsed={false}
        editRequestKey={0}
        onToggleCollapsed={vi.fn()}
      />,
    );
    await screen.findByRole("heading", { name: "成员" });
    expect(screen.queryByPlaceholderText("群名称")).not.toBeInTheDocument();
    rerender(
      <GroupConfigPanel
        roomId="g1"
        roles={roles}
        collapsed={false}
        editRequestKey={1}
        onToggleCollapsed={vi.fn()}
      />,
    );
    expect(await screen.findByPlaceholderText("群名称")).toBeInTheDocument();
  });
});
