import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Role } from "../../api";
import { RoleConfigPanel } from "./RoleConfigPanel";
import { RoleList } from "./RoleList";

afterEach(() => {
  cleanup();
});

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    listRoles: vi.fn(async () => ({
      roles: [
        {
          id: "default",
          name: "通用",
          avatar: null,
          system_prompt: "知识沉淀助手",
          is_default: true,
          sort_order: 0,
          created_at: "2026-08-07T15:00:00+08:00",
          updated_at: "2026-08-07T15:36:00+08:00",
        } satisfies Role,
      ],
    })),
    searchConversations: vi.fn(async () => ({ hits: [] })),
    getRole: vi.fn(async (id: string) => ({
      id,
      name: "通用",
      avatar: null,
      system_prompt: "知识沉淀助手",
      is_default: true,
      sort_order: 0,
      created_at: "2026-08-07T15:00:00+08:00",
      updated_at: "2026-08-07T15:36:00+08:00",
    })),
    listRoleSchedules: vi.fn(async () => ({ schedules: [] })),
  };
});

describe("RoleList", () => {
  it("shows circular list rows with name, preview, and compact time", async () => {
    render(
      <RoleList
        activeRoleId="default"
        onSelectRole={vi.fn()}
        onNewRole={vi.fn()}
      />,
    );
    expect(await screen.findByText("通用")).toBeInTheDocument();
    expect(screen.getByText("知识沉淀助手")).toBeInTheDocument();
    expect(screen.getByLabelText("搜索本角色会话")).toBeInTheDocument();
    expect(screen.getByLabelText("新建角色")).toBeInTheDocument();
  });
});

describe("RoleConfigPanel", () => {
  it("hides the panel when collapsed and shows routines when expanded", async () => {
    const { rerender } = render(
      <RoleConfigPanel
        roleId="default"
        collapsed
        onToggleCollapsed={vi.fn()}
      />,
    );
    expect(document.querySelector(".role-config-panel--collapsed")).toHaveAttribute(
      "hidden",
    );

    rerender(
      <RoleConfigPanel
        roleId="default"
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    );
    expect(
      await screen.findByText("例行任务是这个角色按时间表定期运行的任务。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建例行任务" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "收起角色设置" })).toBeInTheDocument();
  });

  it("opens timing presets instead of a raw hour interval", async () => {
    const user = userEvent.setup();
    render(
      <RoleConfigPanel
        roleId="default"
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    );
    await screen.findByRole("button", { name: "创建例行任务" });
    await user.click(screen.getByRole("button", { name: "创建例行任务" }));
    expect(screen.getByLabelText("何时运行")).toBeInTheDocument();
    expect(screen.getByLabelText("时间（北京时间）")).toBeInTheDocument();
    expect(screen.queryByLabelText("间隔（小时）")).not.toBeInTheDocument();
  });

  it("opens identity editor from the gear", async () => {
    const user = userEvent.setup();
    render(
      <RoleConfigPanel
        roleId="default"
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    );
    await screen.findByText("例行任务是这个角色按时间表定期运行的任务。");
    await user.click(screen.getByRole("button", { name: "角色设置" }));
    expect(screen.getByPlaceholderText("角色名称")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("这个角色是谁、怎么协作…")).toBeInTheDocument();
  });
});
