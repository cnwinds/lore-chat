import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { listCardGrowth, listCards, listPersonaRevisions } from "../../api";
import { KnowledgeCardsTabs } from "./KnowledgeCardsTabs";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    listCards: vi.fn(),
    listCardGrowth: vi.fn(),
    listPersonaRevisions: vi.fn(),
    editCard: vi.fn(),
    forgetCard: vi.fn(),
    confirmCard: vi.fn(),
    rejectCard: vi.fn(),
    restoreCard: vi.fn(),
    rollbackPersonaRevision: vi.fn(),
  };
});

const scope = "persona:p1";

const learnedEntry = {
  id: "g1",
  kind: "learned" as const,
  created_at: "2026-09-20T10:00:00",
  conversation_id: "conv-1",
  conversation_title: "来源会话标题",
  items: [
    {
      action: "new" as const,
      card_id: "c1",
      kind: "domain" as const,
      statement: "新学正文",
      external: false,
      status: "confirmed" as const,
    },
  ],
};

describe("KnowledgeCardsTabs", () => {
  it("inline variant loads each tab with the persona scope", async () => {
    const user = userEvent.setup();
    vi.mocked(listCards).mockResolvedValue({
      scope,
      count: 0,
      faded_count: 0,
      cards: [],
    });
    vi.mocked(listCardGrowth).mockResolvedValue({ scope, entries: [] });
    vi.mocked(listPersonaRevisions).mockResolvedValue({ scope, revisions: [] });

    render(<KnowledgeCardsTabs variant="inline" scope={scope} />);

    expect(await screen.findByRole("tab", { name: "卡片" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "成长" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "人设历史" })).toBeInTheDocument();
    await waitFor(() => {
      expect(listCards).toHaveBeenCalledWith(scope);
    });

    await user.click(screen.getByRole("tab", { name: "成长" }));
    await waitFor(() => {
      expect(listCardGrowth).toHaveBeenCalledWith(scope);
    });

    await user.click(screen.getByRole("tab", { name: "人设历史" }));
    await waitFor(() => {
      expect(listPersonaRevisions).toHaveBeenCalledWith(scope);
    });
  });

  it("does not render conversation jump buttons when onOpenConversation is omitted", async () => {
    const user = userEvent.setup();
    vi.mocked(listCards).mockResolvedValue({
      scope,
      count: 0,
      faded_count: 0,
      cards: [],
    });
    vi.mocked(listCardGrowth).mockResolvedValue({
      scope,
      entries: [learnedEntry],
    });
    vi.mocked(listPersonaRevisions).mockResolvedValue({ scope, revisions: [] });

    render(<KnowledgeCardsTabs variant="inline" scope={scope} />);
    await user.click(await screen.findByRole("tab", { name: "成长" }));
    expect(await screen.findByText("来源会话标题")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "来源会话标题" }),
    ).toBeNull();
  });
});
