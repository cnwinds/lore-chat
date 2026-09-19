import { cleanup, render, screen } from "@testing-library/react";
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

vi.mock("../../api", () => ({
  getContextStats: vi.fn(async () => stats),
}));

afterEach(() => {
  cleanup();
  vi.mocked(getContextStats).mockReset();
  vi.mocked(getContextStats).mockResolvedValue(stats);
});

describe("ContextStatsButton", () => {
  it("lists memory as its own row and peeks injected text", async () => {
    const user = userEvent.setup();
    render(<ContextStatsButton conversationId="c1" />);
    await user.click(screen.getByRole("button", { name: "会话统计" }));
    const memory = await screen.findByRole("button", { name: /记忆/ });
    expect(memory).toHaveTextContent("120");
    expect(
      screen.queryByText("我工作日晚上通常只有约 1 小时可支配"),
    ).toBeNull();
    await user.click(memory);
    expect(
      screen.getByText("- 我工作日晚上通常只有约 1 小时可支配"),
    ).toBeInTheDocument();
  });
});
