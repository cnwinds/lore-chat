import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  confirmCard,
  forgetCard,
  listCards,
  rejectCard,
  type KnowledgeCard,
} from "../../api";
import { KnowledgeCardList } from "./KnowledgeCardList";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    listCards: vi.fn(),
    confirmCard: vi.fn(),
    rejectCard: vi.fn(),
    forgetCard: vi.fn(),
    editCard: vi.fn(),
  };
});

const scope = "role:default";

const sampleConfirmed: KnowledgeCard = {
  id: "c1",
  slot_key: "domain.topic",
  kind: "domain",
  statement: "领域陈述内容足够长",
  origin: "direct",
  external: false,
  status: "confirmed",
  conversation_ids: [],
};

const sampleExternal: KnowledgeCard = {
  ...sampleConfirmed,
  id: "c2",
  kind: "audience",
  origin: "external",
  external: true,
  statement: "来访者常问退款流程",
};

const sampleCandidate: KnowledgeCard = {
  ...sampleConfirmed,
  id: "c3",
  status: "candidate",
  kind: "practice",
  statement: "做法类待印证条目内容",
};

describe("KnowledgeCardList", () => {
  it("renders kind labels, external tag, and pending status", async () => {
    vi.mocked(listCards).mockResolvedValueOnce({
      scope,
      count: 3,
      cards: [sampleConfirmed, sampleExternal, sampleCandidate],
    });
    render(<KnowledgeCardList scope={scope} />);
    expect(await screen.findByText("领域知识")).toBeInTheDocument();
    expect(screen.getByText("受众")).toBeInTheDocument();
    expect(screen.getByText("外部")).toBeInTheDocument();
    expect(screen.getByText("做法")).toBeInTheDocument();
    expect(screen.getByText("待印证")).toBeInTheDocument();
  });

  it("uses knowledge-card menu label for screen readers", async () => {
    const user = userEvent.setup();
    vi.mocked(listCards).mockResolvedValueOnce({
      scope,
      count: 1,
      cards: [sampleConfirmed],
    });
    render(<KnowledgeCardList scope={scope} />);
    await screen.findByText("领域陈述内容足够长");
    await user.click(screen.getByRole("button", { name: "更多操作" }));
    expect(screen.getByRole("menu", { name: "知识卡操作" })).toBeInTheDocument();
  });

  it("shows empty state copy", async () => {
    vi.mocked(listCards).mockResolvedValueOnce({
      scope,
      count: 0,
      cards: [],
    });
    render(<KnowledgeCardList scope={scope} />);
    expect(
      await screen.findByText(
        "还没有知识卡。和这个角色多聊几次，它会自己积累。",
      ),
    ).toBeInTheDocument();
  });

  it("calls confirm with scope for candidate cards", async () => {
    const user = userEvent.setup();
    vi.mocked(listCards)
      .mockResolvedValueOnce({
        scope,
        count: 1,
        cards: [sampleCandidate],
      })
      .mockResolvedValueOnce({
        scope,
        count: 0,
        cards: [],
      });
    vi.mocked(confirmCard).mockResolvedValueOnce({ ok: true });

    render(<KnowledgeCardList scope={scope} />);
    await screen.findByText("待印证");
    await user.click(screen.getByRole("button", { name: "更多操作" }));
    await user.click(screen.getByRole("menuitem", { name: "确认" }));
    await waitFor(() => {
      expect(confirmCard).toHaveBeenCalledWith(scope, "c3");
    });
  });

  it("calls reject with scope for candidate cards", async () => {
    const user = userEvent.setup();
    vi.mocked(listCards)
      .mockResolvedValueOnce({
        scope,
        count: 1,
        cards: [sampleCandidate],
      })
      .mockResolvedValueOnce({
        scope,
        count: 0,
        cards: [],
      });
    vi.mocked(rejectCard).mockResolvedValueOnce({ ok: true });
    window.confirm = vi.fn(() => true);

    render(<KnowledgeCardList scope={scope} />);
    await screen.findByText("待印证");
    await user.click(screen.getByRole("button", { name: "更多操作" }));
    await user.click(screen.getByRole("menuitem", { name: "驳回" }));
    await waitFor(() => {
      expect(rejectCard).toHaveBeenCalledWith(scope, "c3");
    });
  });

  it("calls forget with scope for confirmed cards", async () => {
    const user = userEvent.setup();
    vi.mocked(listCards)
      .mockResolvedValueOnce({
        scope,
        count: 1,
        cards: [sampleConfirmed],
      })
      .mockResolvedValueOnce({
        scope,
        count: 0,
        cards: [],
      });
    vi.mocked(forgetCard).mockResolvedValueOnce({ ok: true });
    window.confirm = vi.fn(() => true);

    render(<KnowledgeCardList scope={scope} />);
    await screen.findByText("领域陈述内容足够长");
    await user.click(screen.getByRole("button", { name: "更多操作" }));
    await user.click(screen.getByRole("menuitem", { name: "遗忘" }));
    await waitFor(() => {
      expect(forgetCard).toHaveBeenCalledWith(scope, "c1");
    });
  });
});
