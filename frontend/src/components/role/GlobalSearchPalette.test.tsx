import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { searchConversations, type Role } from "../../api";
import { GlobalSearchPalette } from "./GlobalSearchPalette";

afterEach(() => {
  cleanup();
  vi.mocked(searchConversations).mockReset();
  vi.mocked(searchConversations).mockResolvedValue({ hits: [], tier: "none" });
});

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    searchConversations: vi.fn(async () => ({ hits: [], tier: "none" })),
  };
});

const sampleRoles: Role[] = [
  {
    id: "default",
    name: "通用助手",
    avatar: null,
    system_prompt: "知识沉淀助手",
    is_default: true,
    sort_order: 0,
    created_at: "2026-08-07T15:00:00+08:00",
    updated_at: "2026-08-07T15:36:00+08:00",
  },
  {
    id: "news",
    name: "新闻助手",
    avatar: null,
    system_prompt: "写快讯",
    is_default: false,
    sort_order: 1,
    created_at: "2026-08-07T15:00:00+08:00",
    updated_at: "2026-08-07T15:36:00+08:00",
  },
];

describe("GlobalSearchPalette", () => {
  it("shows roles when opened with an empty query", async () => {
    render(
      <GlobalSearchPalette
        open
        roles={sampleRoles}
        onClose={vi.fn()}
        onSelectRole={vi.fn()}
        onSearchHit={vi.fn()}
      />,
    );
    expect(await screen.findByLabelText("搜索角色、消息和文件")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "全部" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("通用助手")).toBeInTheDocument();
    expect(screen.getByText("新闻助手")).toBeInTheDocument();
    expect(screen.getAllByText("角色").length).toBeGreaterThan(0);
  });

  it("searches messages with FTS+vector API and jumps on click", async () => {
    const user = userEvent.setup();
    const onSearchHit = vi.fn();
    vi.mocked(searchConversations).mockResolvedValueOnce({
      hits: [
        {
          kind: "message",
          conversation_id: "c1",
          message_id: "m1",
          role_id: "news",
          role_name: "新闻助手",
          title: "对话",
          snippet: "输出的版式考虑格式显示",
          ts: "2026-09-10T12:00:00+08:00",
        },
      ],
      tier: "strong",
    });
    render(
      <GlobalSearchPalette
        open
        roles={sampleRoles}
        onClose={vi.fn()}
        onSelectRole={vi.fn()}
        onSearchHit={onSearchHit}
      />,
    );
    await user.type(screen.getByLabelText("搜索角色、消息和文件"), "浙");
    await waitFor(() => {
      expect(searchConversations).toHaveBeenCalledWith({
        q: "浙",
        k: 16,
        scope: "all",
      });
    });
    expect(await screen.findByText("输出的版式考虑格式显示")).toBeInTheDocument();
    await user.click(screen.getByText("输出的版式考虑格式显示"));
    expect(onSearchHit).toHaveBeenCalledWith(
      expect.objectContaining({ conversation_id: "c1", message_id: "m1" }),
    );
  });

  it("switches to the files tab before querying", async () => {
    const user = userEvent.setup();
    render(
      <GlobalSearchPalette
        open
        roles={sampleRoles}
        onClose={vi.fn()}
        onSelectRole={vi.fn()}
        onSearchHit={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("tab", { name: "文件" }));
    expect(screen.getByText("输入关键词搜索")).toBeInTheDocument();
    await user.type(screen.getByLabelText("搜索角色、消息和文件"), "浙江");
    await waitFor(() => {
      expect(searchConversations).toHaveBeenCalledWith({
        q: "浙江",
        k: 16,
        scope: "files",
      });
    });
  });

  it("restores query, scroll, last hit highlight, and selects the input", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onSearchHit = vi.fn();
    vi.mocked(searchConversations).mockResolvedValue({
      hits: [
        {
          kind: "message",
          conversation_id: "c1",
          message_id: "m1",
          role_id: "news",
          role_name: "新闻助手",
          title: "对话",
          snippet: "第一条结果",
          ts: "2026-09-10T12:00:00+08:00",
        },
        {
          kind: "message",
          conversation_id: "c2",
          message_id: "m2",
          role_id: "news",
          role_name: "新闻助手",
          title: "对话",
          snippet: "第二条结果",
          ts: "2026-09-10T11:00:00+08:00",
        },
      ],
      tier: "strong",
    });
    const props = {
      roles: sampleRoles,
      onClose,
      onSelectRole: vi.fn(),
      onSearchHit,
    };
    const { rerender } = render(<GlobalSearchPalette open {...props} />);
    await user.type(screen.getByLabelText("搜索角色、消息和文件"), "浙");
    expect(await screen.findByText("第二条结果")).toBeInTheDocument();
    const results = document.querySelector(".workspace-search-results");
    expect(results).toBeInstanceOf(HTMLDivElement);
    (results as HTMLDivElement).scrollTop = 48;
    await user.click(screen.getByText("第二条结果"));
    expect(onSearchHit).toHaveBeenCalledWith(
      expect.objectContaining({ conversation_id: "c2", message_id: "m2" }),
    );
    expect(onClose).toHaveBeenCalled();
    rerender(<GlobalSearchPalette open={false} {...props} />);
    rerender(<GlobalSearchPalette open {...props} />);

    const input = await screen.findByLabelText("搜索角色、消息和文件");
    expect(input).toHaveValue("浙");
    const active = screen.getByRole("button", { name: /第二条结果/ });
    expect(active).toHaveClass("is-active");
    expect(active).toHaveAttribute("aria-current", "true");
    await waitFor(() => {
      expect((input as HTMLInputElement).selectionStart).toBe(0);
      expect((input as HTMLInputElement).selectionEnd).toBe(1);
    });
    expect(document.querySelector(".workspace-search-results")?.scrollTop).toBe(
      48,
    );
    expect(searchConversations).toHaveBeenCalledTimes(1);

    await user.type(input, "新");
    expect(input).toHaveValue("新");
  });

  it("opens from the global Ctrl+K shortcut", async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    render(
      <GlobalSearchPalette
        open={false}
        roles={sampleRoles}
        onOpen={onOpen}
        onClose={vi.fn()}
        onSelectRole={vi.fn()}
        onSearchHit={vi.fn()}
      />,
    );
    await user.keyboard("{Control>}k{/Control}");
    expect(onOpen).toHaveBeenCalled();
  });
});
