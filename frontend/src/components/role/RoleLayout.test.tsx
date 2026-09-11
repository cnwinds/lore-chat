import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getRole,
  listRoleScheduleRuns,
  listRoleSchedules,
  listRoles,
  type Role,
  type RoleSchedule,
} from "../../api";
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
    listRoleScheduleRuns: vi.fn(async () => ({ runs: [] })),
  };
});

const sampleSchedule = {
  id: "sched-1",
  role_id: "default",
  prompt: "每日简报",
  interval_hours: 24,
  timing_summary: "每天 09:00",
  enabled: true,
  next_run_at: "2026-08-08T09:00:00+08:00",
  last_run_at: "2026-08-07T09:00:00+08:00",
  created_at: "2026-08-01T10:00:00+08:00",
  updated_at: "2026-08-07T09:00:00+08:00",
} satisfies RoleSchedule;

describe("RoleList", () => {
  it("renders knowledge-base avatars in the list via download URL", async () => {
    const path = "媒体/2026-09/a.png";
    vi.mocked(listRoles).mockResolvedValueOnce({
      roles: [
        {
          id: "default",
          name: "通用",
          avatar: path,
          system_prompt: "知识沉淀助手",
          is_default: true,
          sort_order: 0,
          created_at: "2026-08-07T15:00:00+08:00",
          updated_at: "2026-08-07T15:36:00+08:00",
        } satisfies Role,
      ],
    });
    render(
      <RoleList
        activeRoleId="default"
        onSelectRole={vi.fn()}
        onNewRole={vi.fn()}
      />,
    );
    expect(await screen.findByText("通用")).toBeInTheDocument();
    const img = document.querySelector(".role-item img");
    expect(img?.getAttribute("src")).toContain("/api/download");
    expect(decodeURIComponent(img?.getAttribute("src") || "")).toContain(path);
  });

  it("shows circular list rows with name, preview, and compact time", async () => {
    render(
      <RoleList
        activeRoleId="default"
        onSelectRole={vi.fn()}
        onNewRole={vi.fn()}
      />,
    );
    expect(await screen.findByText("通用")).toBeInTheDocument();
    expect(screen.getByText("暂无对话")).toBeInTheDocument();
    expect(screen.getByLabelText("搜索")).toBeInTheDocument();
    expect(screen.getByLabelText("新建角色")).toBeInTheDocument();
    expect(screen.queryByLabelText("搜索本角色会话")).not.toBeInTheDocument();
  });

  it("opens the search palette from the toolbar icon", async () => {
    const user = userEvent.setup();
    render(
      <RoleList
        activeRoleId="default"
        onSelectRole={vi.fn()}
        onNewRole={vi.fn()}
      />,
    );
    await screen.findByText("通用");
    await user.click(screen.getByLabelText("搜索"));
    expect(
      await screen.findByLabelText("搜索角色、消息和文件"),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "消息" })).toBeInTheDocument();
  });

  it("lists recently active roles first", async () => {
    vi.mocked(listRoles).mockResolvedValueOnce({
      roles: [
        {
          id: "old",
          name: "旧角色",
          avatar: null,
          system_prompt: "旧",
          is_default: false,
          sort_order: 0,
          created_at: "2026-08-01T10:00:00+08:00",
          updated_at: "2026-08-01T10:00:00+08:00",
          last_active_at: "2026-08-01T10:00:00+08:00",
        },
        {
          id: "new",
          name: "新聊的",
          avatar: null,
          system_prompt: "新",
          is_default: false,
          sort_order: 1,
          created_at: "2026-08-02T10:00:00+08:00",
          updated_at: "2026-08-02T10:00:00+08:00",
          last_active_at: "2026-08-07T20:00:00+08:00",
        },
      ],
    });
    render(
      <RoleList
        activeRoleId="new"
        onSelectRole={vi.fn()}
        onNewRole={vi.fn()}
      />,
    );
    const names = (await screen.findAllByText(/旧角色|新聊的/)).map(
      (el) => el.textContent,
    );
    expect(names[0]).toBe("新聊的");
    expect(names[1]).toBe("旧角色");
  });

  it("shows the last reply instead of persona", async () => {
    vi.mocked(listRoles).mockResolvedValueOnce({
      roles: [
        {
          id: "stock",
          name: "股票研究院",
          avatar: null,
          system_prompt: "专注基本面研究",
          last_reply_preview: "今日沪深三百震荡，建议先看成交量。",
          is_default: false,
          sort_order: 1,
          created_at: "2026-08-07T15:00:00+08:00",
          updated_at: "2026-08-07T15:36:00+08:00",
          last_active_at: "2026-08-06T09:05:00+08:00",
        } satisfies Role,
      ],
    });
    render(
      <RoleList
        activeRoleId="stock"
        onSelectRole={vi.fn()}
        onNewRole={vi.fn()}
      />,
    );
    expect(await screen.findByText("股票研究院")).toBeInTheDocument();
    expect(
      screen.getByText("今日沪深三百震荡，建议先看成交量。"),
    ).toBeInTheDocument();
    expect(screen.queryByText("专注基本面研究")).not.toBeInTheDocument();
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
    expect(screen.getByText("通用的屏幕")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建例行任务" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "收起角色设置" })).toBeInTheDocument();
    expect(document.querySelector(".role-config-routines--empty")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "例行任务" })).not.toBeInTheDocument();
  });

  it("resolves a knowledge-base avatar path on the cover", async () => {
    const path = "媒体/2026-09/20260910_084039_74b0c2929.png";
    vi.mocked(getRole).mockImplementation(async (id: string) => ({
      id,
      name: "通用",
      avatar: path,
      system_prompt: "知识沉淀助手",
      is_default: true,
      sort_order: 0,
      created_at: "2026-08-07T15:00:00+08:00",
      updated_at: "2026-08-07T15:36:00+08:00",
    }));
    render(
      <RoleConfigPanel
        roleId="default"
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    );
    await waitFor(() => {
      const img = document.querySelector(".role-config-cover-art img");
      expect(img?.getAttribute("src")).toContain("/api/download");
      expect(decodeURIComponent(img?.getAttribute("src") || "")).toContain(path);
    });
    vi.mocked(getRole).mockImplementation(async (id: string) => ({
      id,
      name: "通用",
      avatar: null,
      system_prompt: "知识沉淀助手",
      is_default: true,
      sort_order: 0,
      created_at: "2026-08-07T15:00:00+08:00",
      updated_at: "2026-08-07T15:36:00+08:00",
    }));
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
    expect(screen.getByRole("heading", { name: "创建例行任务" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText("执行历史")).not.toBeInTheDocument();
  });

  it("opens an existing routine with run history", async () => {
    const user = userEvent.setup();
    vi.mocked(listRoleSchedules).mockResolvedValueOnce({
      schedules: [sampleSchedule],
    });
    vi.mocked(listRoleScheduleRuns).mockResolvedValueOnce({
      runs: [
        {
          turn_id: "t1",
          conversation_id: "c1",
          status: "complete",
          started_at: "2026-08-07T09:00:00+08:00",
          finalized_at: "2026-08-07T09:01:00+08:00",
          summary: "今日无重大事项",
        },
      ],
    });
    render(
      <RoleConfigPanel
        roleId="default"
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    );
    expect(
      await screen.findByRole("heading", { name: "例行任务" }),
    ).toBeInTheDocument();
    expect(screen.getByText("通用的屏幕")).toBeInTheDocument();
    expect(
      screen.queryByText("例行任务是这个角色按时间表定期运行的任务。"),
    ).not.toBeInTheDocument();
    expect(document.querySelector(".role-config-routines--empty")).toBeFalsy();
    expect(screen.getByRole("button", { name: "创建例行任务" })).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: /每日简报/ }));
    expect(await screen.findByRole("heading", { name: "例行任务" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "返回例行任务列表" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText("通用")).not.toBeInTheDocument();
    expect(screen.getByText("执行历史")).toBeInTheDocument();
    expect(await screen.findByText("今日无重大事项")).toBeInTheDocument();
    expect(screen.getByLabelText("何时运行")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "返回例行任务列表" }));
    expect(await screen.findByRole("button", { name: /每日简报/ })).toBeInTheDocument();
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
