import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  acceptCardProposal,
  dismissCardProposal,
  listCardGrowth,
  type CardGrowthEntry,
} from "../../api";
import { CardGrowthTimeline } from "./CardGrowthTimeline";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    listCardGrowth: vi.fn(),
    acceptCardProposal: vi.fn(),
    dismissCardProposal: vi.fn(),
  };
});

const scope = "role:default";

const learnedEntry: CardGrowthEntry = {
  id: "g-learned",
  kind: "learned",
  created_at: "2026-09-20T10:00:00",
  conversation_id: "conv-1",
  conversation_title: "来源会话标题",
  items: [
    {
      action: "new",
      card_id: "c1",
      kind: "domain",
      statement: "新学正文",
      external: false,
      status: "confirmed",
    },
    {
      action: "revised",
      card_id: "c2",
      kind: "practice",
      statement: "修正后正文",
      external: false,
      status: "confirmed",
      previous: "修正前正文",
    },
    {
      action: "promoted",
      card_id: "c3",
      kind: "audience",
      statement: "转正正文",
      external: true,
      status: "confirmed",
    },
    {
      action: "revived",
      card_id: "c4",
      kind: "lesson",
      statement: "恢复正文",
      external: false,
      status: "confirmed",
    },
  ],
};

const consolidatedEntry: CardGrowthEntry = {
  id: "g-consolidated",
  kind: "consolidated",
  created_at: "2026-09-19T10:00:00",
  conversation_id: null,
  conversation_title: null,
  items: [
    {
      action: "merged",
      card_id: "c5",
      kind: "lesson",
      statement: "合并后正文",
      external: false,
      status: "confirmed",
      previous: "合并前正文",
      sources: [
        { card_id: "c6", statement: "被合并卡一" },
        { card_id: "c7", statement: "被合并卡二" },
      ],
    },
    {
      action: "abstracted",
      card_id: "c8",
      kind: "practice",
      statement: "抽象后正文",
      external: false,
      status: "confirmed",
      sources: [{ card_id: "c9", statement: "原卡" }],
    },
    {
      action: "qualified",
      card_id: "c10",
      kind: "domain",
      statement: "补条件后正文",
      external: false,
      status: "confirmed",
      previous: "补条件前正文",
    },
    {
      action: "superseded",
      card_id: "c11",
      kind: "domain",
      statement: "取代后正文",
      external: false,
      status: "confirmed",
      sources: [{ card_id: "c12", statement: "被取代卡" }],
    },
  ],
};

const fadedEntry: CardGrowthEntry = {
  id: "g-faded",
  kind: "faded",
  created_at: "2026-09-18T10:00:00",
  conversation_id: null,
  conversation_title: null,
  items: [
    {
      action: "expired",
      card_id: "c13",
      kind: "lesson",
      statement: "过期正文",
      external: false,
      status: "confirmed",
    },
    {
      action: "dropped",
      card_id: "c14",
      kind: "audience",
      statement: "作废正文",
      external: true,
      status: "candidate",
    },
  ],
};

describe("CardGrowthTimeline", () => {
  it("renders entry kinds, action labels, previous, and sources", async () => {
    const user = userEvent.setup();
    vi.mocked(listCardGrowth).mockResolvedValueOnce({
      scope,
      entries: [learnedEntry, consolidatedEntry, fadedEntry],
    });

    render(<CardGrowthTimeline scope={scope} />);

    expect(await screen.findByText("学到")).toBeInTheDocument();
    expect(screen.getByText("整理")).toBeInTheDocument();
    expect(screen.getByText("淡出")).toBeInTheDocument();

    expect(screen.getByText("新学")).toBeInTheDocument();
    expect(screen.getByText("修正")).toBeInTheDocument();
    expect(screen.getByText("转正")).toBeInTheDocument();
    expect(screen.getByText("恢复")).toBeInTheDocument();
    expect(screen.getByText("合并")).toBeInTheDocument();
    expect(screen.getByText("抽象")).toBeInTheDocument();
    expect(screen.getByText("补条件")).toBeInTheDocument();
    expect(screen.getByText("取代")).toBeInTheDocument();
    expect(screen.getByText("过期")).toBeInTheDocument();
    expect(screen.getByText("作废")).toBeInTheDocument();

    expect(screen.getByText("原：修正前正文")).toBeInTheDocument();
    expect(screen.getByText("原：合并前正文")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "由 2 张卡整理而来" }));
    expect(screen.getByText("被合并卡一")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "取代了 1 张卡" }));
    expect(screen.getByText("被取代卡")).toBeInTheDocument();
  });

  it("calls onOpenConversation for learned entries with a conversation", async () => {
    const user = userEvent.setup();
    const onOpenConversation = vi.fn();
    vi.mocked(listCardGrowth).mockResolvedValueOnce({
      scope,
      entries: [learnedEntry],
    });

    render(
      <CardGrowthTimeline
        scope={scope}
        onOpenConversation={onOpenConversation}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "来源会话标题" }));
    expect(onOpenConversation).toHaveBeenCalledWith("conv-1");
  });

  it("uses conversation title when present and keeps the button enabled", async () => {
    vi.mocked(listCardGrowth).mockResolvedValueOnce({
      scope,
      entries: [learnedEntry],
    });

    render(<CardGrowthTimeline scope={scope} />);
    const btn = await screen.findByRole("button", { name: "来源会话标题" });
    expect(btn).toBeEnabled();
  });

  it("shows fallback label and stays enabled when conversation title is empty", async () => {
    const user = userEvent.setup();
    const onOpenConversation = vi.fn();
    vi.mocked(listCardGrowth).mockResolvedValueOnce({
      scope,
      entries: [
        {
          ...learnedEntry,
          conversation_title: "",
        },
      ],
    });

    render(
      <CardGrowthTimeline
        scope={scope}
        onOpenConversation={onOpenConversation}
      />,
    );
    const btn = await screen.findByRole("button", { name: "来源会话" });
    expect(btn).toBeEnabled();
    await user.click(btn);
    expect(onOpenConversation).toHaveBeenCalledWith("conv-1");
  });

  it("disables conversation button when conversation was deleted", async () => {
    vi.mocked(listCardGrowth).mockResolvedValueOnce({
      scope,
      entries: [
        {
          ...learnedEntry,
          conversation_title: null,
        },
      ],
    });

    render(<CardGrowthTimeline scope={scope} />);
    const btn = await screen.findByRole("button", { name: "来源会话" });
    expect(btn).toBeDisabled();
  });

  it("renders persona evolved and rolled_back items", async () => {
    const onOpenPersonaHistory = vi.fn();
    vi.mocked(listCardGrowth).mockResolvedValueOnce({
      scope,
      entries: [
        {
          id: "g-persona",
          kind: "persona",
          created_at: "2026-09-17T10:00:00",
          conversation_id: null,
          conversation_title: null,
          items: [
            {
              action: "evolved",
              revision_id: "rev-1",
              op: "insert",
              reason: "补充职责描述",
              before: "",
              after: "新增句",
              basis: ["依据卡"],
            },
            {
              action: "rolled_back",
              revision_id: "rev-old",
              rollback_revision_id: "rev-rb",
              source: "evolution",
            },
          ],
        },
      ],
    });

    const user = userEvent.setup();
    render(
      <CardGrowthTimeline
        scope={scope}
        onOpenPersonaHistory={onOpenPersonaHistory}
      />,
    );

    expect(await screen.findByText("人设")).toBeInTheDocument();
    expect(screen.getByText("补充职责描述")).toBeInTheDocument();
    expect(screen.getByText("新增句")).toBeInTheDocument();
    expect(screen.getByText("回退了一次自动进化改动")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "在人设历史里查看" }));
    expect(onOpenPersonaHistory).toHaveBeenCalled();
  });

  it("accepts proposal with request_text and dismisses pending proposals", async () => {
    const user = userEvent.setup();
    const onUseProposal = vi.fn();
    vi.mocked(listCardGrowth)
      .mockResolvedValueOnce({
        scope,
        entries: [
          {
            id: "g-proposal",
            kind: "proposal",
            created_at: "2026-09-16T10:00:00",
            conversation_id: null,
            conversation_title: null,
            items: [
              {
                action: "proposed",
                proposal_id: "p1",
                target: "skill",
                title: "报价流程",
                reason: "多步可复用",
                basis: ["卡一"],
                status: "pending",
              },
              {
                action: "proposed",
                proposal_id: "p2",
                target: "doc",
                title: "资料清单",
                reason: "便于翻阅",
                basis: ["卡二"],
                status: "dismissed",
              },
            ],
          },
        ],
      })
      .mockResolvedValueOnce({ scope, entries: [] });
    vi.mocked(acceptCardProposal).mockResolvedValueOnce({
      ok: true,
      request_text: "请把下面这些经验固化为一个 Skill",
    });
    vi.mocked(dismissCardProposal).mockResolvedValueOnce({ ok: true });

    render(
      <CardGrowthTimeline scope={scope} onUseProposal={onUseProposal} />,
    );

    expect(await screen.findByText("提议")).toBeInTheDocument();
    expect(
      screen.getByText("提议固化为 Skill「报价流程」"),
    ).toBeInTheDocument();
    expect(screen.getByText("已忽略")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "接受" }));
    await waitFor(() => {
      expect(acceptCardProposal).toHaveBeenCalledWith(scope, "p1");
      expect(onUseProposal).toHaveBeenCalledWith(
        "请把下面这些经验固化为一个 Skill",
      );
    });
  });

  it("hides accept without onUseProposal and calls dismiss", async () => {
    const user = userEvent.setup();
    vi.mocked(listCardGrowth)
      .mockResolvedValueOnce({
        scope,
        entries: [
          {
            id: "g-proposal",
            kind: "proposal",
            created_at: "2026-09-16T10:00:00",
            conversation_id: null,
            conversation_title: null,
            items: [
              {
                action: "proposed",
                proposal_id: "p3",
                target: "doc",
                title: "另一文档",
                reason: "理由",
                basis: [],
                status: "pending",
              },
            ],
          },
        ],
      })
      .mockResolvedValueOnce({ scope, entries: [] });
    vi.mocked(dismissCardProposal).mockResolvedValueOnce({ ok: true });

    render(<CardGrowthTimeline scope={scope} />);
    await screen.findByText("提议写成文档「另一文档」");
    expect(screen.queryByRole("button", { name: "接受" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "忽略" }));
    await waitFor(() => {
      expect(dismissCardProposal).toHaveBeenCalledWith(scope, "p3");
    });
  });

  it("shows empty state copy", async () => {
    vi.mocked(listCardGrowth).mockResolvedValueOnce({ scope, entries: [] });
    render(<CardGrowthTimeline scope={scope} />);
    expect(
      await screen.findByText(
        "还没有成长记录。卡片被学到、整理或淡出时会记在这里。",
      ),
    ).toBeInTheDocument();
  });
});
