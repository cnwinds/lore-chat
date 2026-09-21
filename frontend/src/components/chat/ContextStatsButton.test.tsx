import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getContextStats } from "../../api";
import { ContextStatsButton } from "./ContextStatsButton";

const stats = {
  model: "demo",
  context: { used_tokens: 1000, limit_tokens: 8000 },
  segments: [
    { key: "system", label: "系统提示词", tokens: 400 },
    {
      key: "memory",
      label: "记忆",
      tokens: 120,
      preview: "- 我工作日晚上通常只有约 1 小时可支配",
    },
    { key: "skill", label: "Skill", tokens: 0 },
    { key: "history", label: "历史消息", tokens: 300 },
    { key: "tools", label: "工具与检索结果", tokens: 180 },
    { key: "attachments", label: "附件与文档", tokens: 0 },
  ],
  cache_hit_rate: null,
  tool_calls: 0,
  cost_total: null,
  turns_with_usage: 1,
};

const statsWithTexts = {
  ...stats,
  segments: stats.segments.map((seg) =>
    seg.key === "memory"
      ? { ...seg, text: "- 我工作日晚上通常只有约 1 小时可支配" }
      : seg.key === "history"
        ? { ...seg, text: "用户：你好" }
        : seg,
  ),
};

vi.mock("../../api", () => ({
  getContextStats: vi.fn(async () => stats),
}));

afterEach(() => {
  cleanup();
  vi.mocked(getContextStats).mockReset();
  vi.mocked(getContextStats).mockResolvedValue(stats);
});

async function openPopover(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "会话统计" }));
  return screen.findAllByTitle(/查看.*的注入全文/);
}

describe("ContextStatsButton", () => {
  it("lists every segment as a uniform peek row", async () => {
    const user = userEvent.setup();
    render(<ContextStatsButton conversationId="c1" />);
    const rows = await openPopover(user);
    expect(rows).toHaveLength(6);
    const memory = rows.find((r) => r.textContent?.includes("记忆"));
    expect(memory).toHaveTextContent("120");
  });

  it("opens the inspector with the injected text of a segment", async () => {
    const user = userEvent.setup();
    vi.mocked(getContextStats).mockImplementation(
      async (_cid: string, options?: { includeTexts?: boolean }) =>
        options?.includeTexts ? statsWithTexts : stats,
    );
    render(<ContextStatsButton conversationId="c1" />);
    const rows = await openPopover(user);
    await user.click(rows.find((r) => r.textContent?.includes("记忆"))!);
    expect(
      await screen.findByRole("dialog", { name: "上下文构成" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/我工作日晚上通常只有约 1 小时可支配/),
    ).toBeInTheDocument();
    await waitFor(() => {
      const calls = vi.mocked(getContextStats).mock.calls;
      expect(
        calls.some(([, opts]) => (opts as { includeTexts?: boolean })?.includeTexts),
      ).toBe(true);
    });
  });

  it("shows the all-in view with sections and a skipped note", async () => {
    const user = userEvent.setup();
    vi.mocked(getContextStats).mockImplementation(
      async (_cid: string, options?: { includeTexts?: boolean }) =>
        options?.includeTexts ? statsWithTexts : stats,
    );
    render(<ContextStatsButton conversationId="c1" />);
    const rows = await openPopover(user);
    await user.click(rows[0]);
    await screen.findByRole("dialog", { name: "上下文构成" });
    // 点具体行默认定位到该分段；切「全文」后按注入顺序铺开并标注未注入项
    await user.click(screen.getByRole("button", { name: "全文" }));
    expect(await screen.findByText(/用户：你好/)).toBeInTheDocument();
    expect(
      screen.getByText(/Skill、工具与检索结果、附件与文档：本轮未注入/),
    ).toBeInTheDocument();
  });

  it("closes the inspector with the close button", async () => {
    const user = userEvent.setup();
    vi.mocked(getContextStats).mockImplementation(
      async (_cid: string, options?: { includeTexts?: boolean }) =>
        options?.includeTexts ? statsWithTexts : stats,
    );
    render(<ContextStatsButton conversationId="c1" />);
    const rows = await openPopover(user);
    await user.click(rows[0]);
    await screen.findByRole("dialog", { name: "上下文构成" });
    await user.click(screen.getByRole("button", { name: "关闭" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "上下文构成" })).toBeNull();
    });
  });
});
