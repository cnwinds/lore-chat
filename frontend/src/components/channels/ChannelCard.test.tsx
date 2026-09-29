import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChannelInstance, ChannelType } from "../../api/channelPlugins";
import { ChannelCard } from "./ChannelCard";

afterEach(() => {
  cleanup();
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
  onToggleOutput = vi.fn(),
) {
  return render(
    <ChannelCard
      inst={{ ...baseInst, ...overrides }}
      types={types}
      personas={[]}
      usage={new Map()}
      busy={false}
      activeTab={null}
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
    />,
  );
}

describe("ChannelCard", () => {
  it("owner memory switch defaults off and toggles include_owner_memory", async () => {
    const user = userEvent.setup();
    const onToggleOutput = vi.fn();
    renderCard({ include_owner_memory: false }, onToggleOutput);
    const toggle = screen.getByRole("switch", { name: "带上主人记忆" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    await user.click(toggle);
    expect(onToggleOutput).toHaveBeenCalledWith(
      expect.objectContaining({ id: "inst-1" }),
      "include_owner_memory",
    );
  });
});
