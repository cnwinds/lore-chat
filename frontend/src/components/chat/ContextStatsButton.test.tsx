import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getContextStats } from "../../api";
import { ContextStatsButton } from "./ContextStatsButton";

const stats = {
  model: "demo",
  context: { used_tokens: 1000, limit_tokens: 8000 },
  segments: [
    { key: "rules", label: "系统规约", tokens: 400 },
    { key: "history", label: "历史对话", tokens: 300 },
  ],
  latest_call_id: 7,
  captured_at: "2026-01-01T00:00:00Z",
  cache_hit_rate: null,
  tool_calls: 0,
  cost_total: null,
  turns_with_usage: 1,
};

vi.mock("../../api", () => ({
  getContextStats: vi.fn(async () => stats),
  listConversationRequests: vi.fn(async () => ({ calls: [] })),
  getConversationRequest: vi.fn(),
  getConversationRequestRaw: vi.fn(),
}));

vi.mock("./request-inspector/RequestInspectorModal", () => ({
  RequestInspectorModal: ({ open }: { open: boolean }) =>
    open ? <div role="dialog" aria-label="发送内容">inspector</div> : null,
}));

afterEach(() => {
  cleanup();
  vi.mocked(getContextStats).mockReset();
  vi.mocked(getContextStats).mockResolvedValue(stats);
});

describe("ContextStatsButton", () => {
  it("分项带约等于并打开检查器", async () => {
    const user = userEvent.setup();
    render(<ContextStatsButton conversationId="c1" />);
    await user.click(screen.getByRole("button", { name: "会话统计" }));
    expect(await screen.findByText(/≈400/)).toBeInTheDocument();
    await user.click(screen.getByText("系统规约"));
    expect(screen.getByRole("dialog", { name: "发送内容" })).toBeInTheDocument();
  });

  it("无采集时显示占位", async () => {
    vi.mocked(getContextStats).mockResolvedValue({
      ...stats,
      segments: [],
      latest_call_id: null,
    });
    const user = userEvent.setup();
    render(<ContextStatsButton conversationId="c1" />);
    await user.click(screen.getByRole("button", { name: "会话统计" }));
    expect(await screen.findByText("发出消息后显示")).toBeInTheDocument();
  });

  it("streaming 结束后重新拉统计", async () => {
    const { rerender } = render(
      <ContextStatsButton conversationId="c1" streaming={true} />,
    );
    await waitFor(() => expect(getContextStats).toHaveBeenCalled());
    const n = vi.mocked(getContextStats).mock.calls.length;
    rerender(<ContextStatsButton conversationId="c1" streaming={false} />);
    await waitFor(() =>
      expect(vi.mocked(getContextStats).mock.calls.length).toBeGreaterThan(n),
    );
  });
});
