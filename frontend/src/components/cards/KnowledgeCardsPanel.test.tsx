import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { listCardGrowth, listCards, listPersonaRevisions } from "../../api";
import { KnowledgeCardsPanel } from "./KnowledgeCardsPanel";

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
  };
});

const scope = "role:default";

describe("KnowledgeCardsPanel", () => {
  it("switches tabs and shows meta copy for cards and growth", async () => {
    const user = userEvent.setup();
    vi.mocked(listCards).mockResolvedValue({
      scope,
      count: 2,
      faded_count: 1,
      cards: [
        {
          id: "c1",
          slot_key: "domain.topic",
          kind: "domain",
          statement: "活跃卡一",
          origin: "direct",
          external: false,
          status: "confirmed",
          merged_into_persona: false,
          conversation_ids: [],
        },
        {
          id: "c2",
          slot_key: "practice.topic",
          kind: "practice",
          statement: "活跃卡二",
          origin: "direct",
          external: false,
          status: "candidate",
          merged_into_persona: false,
          conversation_ids: [],
        },
        {
          id: "c3",
          slot_key: "lesson.topic",
          kind: "lesson",
          statement: "淡出卡",
          origin: "direct",
          external: false,
          status: "stale",
          merged_into_persona: false,
          conversation_ids: [],
        },
      ],
    });
    vi.mocked(listPersonaRevisions).mockResolvedValue({ scope, revisions: [] });
    vi.mocked(listCardGrowth).mockResolvedValue({
      scope,
      entries: [
        {
          id: "g1",
          kind: "learned",
          created_at: "2026-09-20T10:00:00",
          conversation_id: "conv-1",
          conversation_title: "测试会话",
          items: [
            {
              action: "new",
              card_id: "c1",
              kind: "domain",
              statement: "新学到的卡",
              external: false,
              status: "confirmed",
            },
          ],
        },
      ],
    });

    render(
      <KnowledgeCardsPanel
        scope={scope}
        title="测试角色"
        onClose={() => undefined}
      />,
    );

    expect(await screen.findByText("2 条 · 已淡出 1")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "卡片" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    await user.click(screen.getByRole("tab", { name: "成长" }));
    expect(await screen.findByText("1 条记录")).toBeInTheDocument();
    expect(screen.getByText("学到")).toBeInTheDocument();
  });

  it("switches to persona history tab and shows version meta", async () => {
    const user = userEvent.setup();
    vi.mocked(listCards).mockResolvedValue({
      scope,
      count: 0,
      faded_count: 0,
      cards: [],
    });
    vi.mocked(listCardGrowth).mockResolvedValue({ scope, entries: [] });
    vi.mocked(listPersonaRevisions).mockResolvedValue({
      scope,
      revisions: [
        {
          id: "r1",
          source: "manual",
          created_at: "2026-09-20T10:00:00",
          body: "人设",
          previous_body: "",
          rolled_back: false,
          can_rollback: false,
          reasons: [],
          reverts: null,
        },
        {
          id: "r2",
          source: "create",
          created_at: "2026-09-19T10:00:00",
          body: "初始",
          previous_body: "",
          rolled_back: false,
          can_rollback: false,
          reasons: [],
          reverts: null,
        },
      ],
    });

    render(
      <KnowledgeCardsPanel
        scope={scope}
        title="测试角色"
        onClose={() => undefined}
      />,
    );

    await user.click(screen.getByRole("tab", { name: "人设历史" }));
    expect(await screen.findByText("2 个版本")).toBeInTheDocument();
    expect(screen.getByText("主人修改")).toBeInTheDocument();
  });

  it("shows empty meta when there are no cards or growth entries", async () => {
    const user = userEvent.setup();
    vi.mocked(listCards).mockResolvedValue({
      scope,
      count: 0,
      faded_count: 0,
      cards: [],
    });
    vi.mocked(listCardGrowth).mockResolvedValue({ scope, entries: [] });
    vi.mocked(listPersonaRevisions).mockResolvedValue({ scope, revisions: [] });

    render(
      <KnowledgeCardsPanel
        scope={scope}
        title="测试角色"
        onClose={() => undefined}
      />,
    );

    expect(await screen.findByText("暂无条目")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "成长" }));
    await waitFor(() => {
      expect(screen.getByText("暂无记录")).toBeInTheDocument();
    });
  });
});
