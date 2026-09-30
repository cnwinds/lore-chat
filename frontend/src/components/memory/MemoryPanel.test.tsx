import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  listCardGrowth,
  listMemoryFacts,
  OWNER_GROWTH_SCOPE,
  restoreMemoryFact,
} from "../../api";
import { MemoryPanel } from "./MemoryPanel";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    listMemoryFacts: vi.fn(),
    listCardGrowth: vi.fn(),
    restoreMemoryFact: vi.fn(),
    confirmMemoryFact: vi.fn(),
    rejectMemoryFact: vi.fn(),
    editMemoryFact: vi.fn(),
    forgetMemoryFact: vi.fn(),
  };
});

const activeFact = {
  id: "f1",
  slot_key: "preference.style",
  statement: "偏好简洁回答",
  category: "preference",
  origin: "direct",
  status: "confirmed",
  conversation_ids: [],
};

const staleFact = {
  id: "f2",
  slot_key: "goal.old",
  statement: "已淡出目标",
  category: "goal",
  origin: "direct",
  status: "stale",
  conversation_ids: [],
};

describe("MemoryPanel", () => {
  it("shows memory and growth tabs", async () => {
    vi.mocked(listMemoryFacts).mockResolvedValueOnce({
      facts: [activeFact],
      count: 1,
      stale: [],
    });
    vi.mocked(listCardGrowth).mockResolvedValueOnce({
      scope: OWNER_GROWTH_SCOPE,
      entries: [],
    });

    render(<MemoryPanel onClose={() => undefined} />);
    expect(await screen.findByRole("tab", { name: "记忆" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "成长" })).toBeInTheDocument();
  });

  it("loads growth with owner scope on growth tab", async () => {
    const user = userEvent.setup();
    vi.mocked(listMemoryFacts).mockResolvedValueOnce({
      facts: [activeFact],
      count: 1,
      stale: [],
    });
    vi.mocked(listCardGrowth).mockResolvedValueOnce({
      scope: OWNER_GROWTH_SCOPE,
      entries: [],
    });

    render(<MemoryPanel onClose={() => undefined} />);
    await user.click(await screen.findByRole("tab", { name: "成长" }));
    await waitFor(() => {
      expect(listCardGrowth).toHaveBeenCalledWith(OWNER_GROWTH_SCOPE);
    });
  });

  it("expands stale section and restores", async () => {
    const user = userEvent.setup();
    const onAttentionChange = vi.fn();
    vi.mocked(listMemoryFacts)
      .mockResolvedValueOnce({
        facts: [activeFact],
        count: 1,
        stale: [staleFact],
      })
      .mockResolvedValueOnce({
        facts: [activeFact, { ...staleFact, status: "confirmed" }],
        count: 2,
        stale: [],
      });
    vi.mocked(restoreMemoryFact).mockResolvedValueOnce({ ok: true });

    render(
      <MemoryPanel onClose={() => undefined} onAttentionChange={onAttentionChange} />,
    );
    expect(await screen.findByText(/已淡出 1/)).toBeInTheDocument();
    expect(screen.queryByText("已淡出目标")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "已淡出 · 1" }));
    expect(await screen.findByText("已淡出目标")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "更多操作" })[1]);
    await user.click(screen.getByRole("menuitem", { name: "恢复" }));
    await waitFor(() => {
      expect(restoreMemoryFact).toHaveBeenCalledWith("f2");
      expect(onAttentionChange).toHaveBeenCalledTimes(1);
    });
    expect(listMemoryFacts).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("button", { name: "已淡出 · 1" })).toBeNull();
    expect(await screen.findByText("2 条已确认")).toBeInTheDocument();
  });
});
