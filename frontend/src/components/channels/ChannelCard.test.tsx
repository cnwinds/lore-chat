import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  listCardGrowth,
  listCards,
  listPersonaRevisions,
  rollbackPersonaRevision,
} from "../../api";
import type { ChannelInstance, ChannelType } from "../../api/channelPlugins";
import { ChannelCard } from "./ChannelCard";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    listCards: vi.fn(),
    listCardGrowth: vi.fn(),
    listPersonaRevisions: vi.fn(),
    rollbackPersonaRevision: vi.fn(),
    editCard: vi.fn(),
    forgetCard: vi.fn(),
    confirmCard: vi.fn(),
    rejectCard: vi.fn(),
    restoreCard: vi.fn(),
  };
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const types: ChannelType[] = [
  {
    type_id: "script_api",
    display_name: "脚本",
    ingress: "http",
    needs_public_url: false,
    available: true,
  },
];

const baseInst: ChannelInstance = {
  id: "inst-1",
  type_id: "script_api",
  name: "测试通道",
  enabled: true,
  status: "enabled",
  persona_id: "p1",
  created_at: "2026-01-01T00:00:00Z",
};

function renderCard(
  overrides: Partial<ChannelInstance> = {},
  options: {
    onToggleOutput?: (
      inst: ChannelInstance,
      field: "show_thinking" | "show_tool_output" | "include_owner_memory",
    ) => void;
    activeTab?: "cards" | null;
    onPersonaMutated?: () => void;
  } = {},
) {
  const onToggleOutput = options.onToggleOutput ?? vi.fn<
    (
      inst: ChannelInstance,
      field: "show_thinking" | "show_tool_output" | "include_owner_memory",
    ) => void
  >();
  return render(
    <ChannelCard
      inst={{ ...baseInst, ...overrides }}
      types={types}
      personas={[]}
      usage={new Map()}
      busy={false}
      activeTab={options.activeTab ?? null}
      editingPrompt={false}
      editName=""
      editPrompt=""
      onToggle={vi.fn()}
      onToggleOutput={onToggleOutput}
      onCopy={vi.fn()}
      onToggleTab={vi.fn()}
      onSelectPersona={vi.fn()}
      onStartEditPrompt={vi.fn()}
      onEditName={vi.fn()}
      onEditPrompt={vi.fn()}
      onSavePrompt={vi.fn()}
      onCancelEditPrompt={vi.fn()}
      onRevoke={vi.fn()}
      onPersonaMutated={options.onPersonaMutated}
    />,
  );
}

describe("ChannelCard", () => {
  it("owner memory switch defaults off and toggles include_owner_memory", async () => {
    const user = userEvent.setup();
    const onToggleOutput = vi.fn();
    renderCard({ include_owner_memory: false }, { onToggleOutput });
    const toggle = screen.getByRole("switch", { name: "带上主人记忆" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    await user.click(toggle);
    expect(onToggleOutput).toHaveBeenCalledWith(
      expect.objectContaining({ id: "inst-1" }),
      "include_owner_memory",
    );
  });

  it("shows knowledge card sub-tabs when the cards detail tab is open", async () => {
    vi.mocked(listCards).mockResolvedValue({
      scope: "persona:p1",
      count: 0,
      faded_count: 0,
      cards: [],
    });
    vi.mocked(listCardGrowth).mockResolvedValue({
      scope: "persona:p1",
      entries: [],
    });
    vi.mocked(listPersonaRevisions).mockResolvedValue({
      scope: "persona:p1",
      revisions: [],
    });

    renderCard({}, { activeTab: "cards" });

    expect(await screen.findByRole("tab", { name: "卡片" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "成长" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "人设历史" })).toBeInTheDocument();
  });

  it("calls onPersonaMutated once after persona history rollback succeeds", async () => {
    const user = userEvent.setup();
    const onPersonaMutated = vi.fn();
    vi.mocked(listCards).mockResolvedValue({
      scope: "persona:p1",
      count: 0,
      faded_count: 0,
      cards: [],
    });
    vi.mocked(listCardGrowth).mockResolvedValue({
      scope: "persona:p1",
      entries: [],
    });
    vi.mocked(listPersonaRevisions)
      .mockResolvedValueOnce({
        scope: "persona:p1",
        revisions: [
          {
            id: "rev-1",
            source: "evolution",
            created_at: "2026-09-20T10:00:00",
            body: "新人设",
            previous_body: "旧人设",
            rolled_back: false,
            can_rollback: true,
            reasons: [],
            reverts: null,
          },
        ],
      })
      .mockResolvedValueOnce({ scope: "persona:p1", revisions: [] });
    vi.mocked(rollbackPersonaRevision).mockResolvedValueOnce({
      ok: true,
      body: "旧人设",
      revision: {
        id: "rev-1",
        source: "evolution",
        created_at: "2026-09-20T10:00:00",
        body: "旧人设",
        previous_body: "新人设",
        rolled_back: false,
        can_rollback: false,
        reasons: [],
        reverts: null,
      },
    });
    window.confirm = vi.fn(() => true);

    renderCard({}, { activeTab: "cards", onPersonaMutated });
    await user.click(await screen.findByRole("tab", { name: "人设历史" }));
    await user.click(await screen.findByRole("button", { name: "回退" }));

    await waitFor(() => {
      expect(rollbackPersonaRevision).toHaveBeenCalledWith("persona:p1", "rev-1");
      expect(onPersonaMutated).toHaveBeenCalledTimes(1);
    });
  });
});
