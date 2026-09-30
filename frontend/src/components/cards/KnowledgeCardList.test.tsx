import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  confirmCard,
  forgetCard,
  listCards,
  rejectCard,
  restoreCard,
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
    restoreCard: vi.fn(),
    editCard: vi.fn(),
  };
});

const scope = "role:default";

function mockList(data: {
  count: number;
  faded_count?: number;
  cards: KnowledgeCard[];
}) {
  return vi.mocked(listCards).mockResolvedValueOnce({
    scope,
    faded_count: data.faded_count ?? 0,
    ...data,
  });
}

const sampleConfirmed: KnowledgeCard = {
  id: "c1",
  slot_key: "domain.topic",
  kind: "domain",
  statement: "领域陈述内容足够长",
  origin: "direct",
  external: false,
  status: "confirmed",
  merged_into_persona: false,
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

const sampleStale: KnowledgeCard = {
  ...sampleConfirmed,
  id: "c4",
  status: "stale",
  statement: "已淡出的知识卡内容",
};

describe("KnowledgeCardList", () => {
  it("shows merged_into_persona tag", async () => {
    mockList({
      count: 1,
      cards: [{ ...sampleConfirmed, merged_into_persona: true }],
    });
    render(<KnowledgeCardList scope={scope} />);
    expect(await screen.findByText("已并入人设")).toBeInTheDocument();
  });

  it("renders kind labels, external tag, and pending status", async () => {
    mockList({
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
    mockList({ count: 1, cards: [sampleConfirmed] });
    render(<KnowledgeCardList scope={scope} />);
    await screen.findByText("领域陈述内容足够长");
    await user.click(screen.getByRole("button", { name: "更多操作" }));
    expect(screen.getByRole("menu", { name: "知识卡操作" })).toBeInTheDocument();
  });

  it("shows empty state copy", async () => {
    mockList({ count: 0, cards: [] });
    render(<KnowledgeCardList scope={scope} />);
    expect(
      await screen.findByText(
        "还没有知识卡。和这个角色多聊几次，它会自己积累。",
      ),
    ).toBeInTheDocument();
  });

  it("calls confirm with scope for candidate cards", async () => {
    const user = userEvent.setup();
    mockList({ count: 1, cards: [sampleCandidate] });
    mockList({ count: 0, cards: [] });
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
    mockList({ count: 1, cards: [sampleCandidate] });
    mockList({ count: 0, cards: [] });
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
    mockList({ count: 1, cards: [sampleConfirmed] });
    mockList({ count: 0, cards: [] });
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

  it("reports count from API without counting stale cards", async () => {
    const onCountChange = vi.fn();
    mockList({
      count: 2,
      faded_count: 1,
      cards: [sampleConfirmed, sampleCandidate, sampleStale],
    });
    render(<KnowledgeCardList scope={scope} onCountChange={onCountChange} />);
    await screen.findByText("领域陈述内容足够长");
    await waitFor(() => {
      expect(onCountChange).toHaveBeenCalledWith(2);
    });
  });

  it("keeps stale cards in a collapsed group by default", async () => {
    mockList({
      count: 1,
      faded_count: 1,
      cards: [sampleConfirmed, sampleStale],
    });
    render(<KnowledgeCardList scope={scope} />);
    await screen.findByText("领域陈述内容足够长");
    expect(screen.getByRole("button", { name: "已淡出 · 1" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByText("已淡出的知识卡内容")).not.toBeInTheDocument();
  });

  it("shows restore and forget only for expanded stale cards", async () => {
    const user = userEvent.setup();
    mockList({
      count: 0,
      faded_count: 1,
      cards: [sampleStale],
    });
    render(<KnowledgeCardList scope={scope} />);
    await user.click(await screen.findByRole("button", { name: "已淡出 · 1" }));
    expect(await screen.findByText("已淡出的知识卡内容")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "更多操作" }));
    expect(screen.getByRole("menuitem", { name: "恢复" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "遗忘" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "编辑" })).not.toBeInTheDocument();
  });

  it("does not render conversation jump when onOpenConversation is omitted", async () => {
    mockList({
      count: 1,
      cards: [
        {
          ...sampleConfirmed,
          conversation_ids: ["conv-1"],
        },
      ],
    });
    render(<KnowledgeCardList scope={scope} />);
    expect(await screen.findByText("领域陈述内容足够长")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "打开来源会话" }),
    ).toBeNull();
  });

  it("calls restoreCard with scope for stale cards", async () => {
    const user = userEvent.setup();
    mockList({ count: 0, faded_count: 1, cards: [sampleStale] });
    mockList({ count: 1, faded_count: 0, cards: [sampleConfirmed] });
    vi.mocked(restoreCard).mockResolvedValueOnce({ ok: true });

    render(<KnowledgeCardList scope={scope} />);
    await user.click(await screen.findByRole("button", { name: "已淡出 · 1" }));
    await screen.findByText("已淡出的知识卡内容");
    await user.click(screen.getByRole("button", { name: "更多操作" }));
    await user.click(screen.getByRole("menuitem", { name: "恢复" }));
    await waitFor(() => {
      expect(restoreCard).toHaveBeenCalledWith(scope, "c4");
    });
  });
});
