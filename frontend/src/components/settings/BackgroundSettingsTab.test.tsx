import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api";
import { SETTINGS_TABS } from "../../hooks/settings/settingsTabStorage";
import { BackgroundSettingsTab } from "./BackgroundSettingsTab";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    getBackgroundStatus: vi.fn(),
  };
});

const getBackgroundStatus = vi.mocked(api.getBackgroundStatus);

describe("BackgroundSettingsTab", () => {
  beforeEach(() => {
    getBackgroundStatus.mockReset();
    getBackgroundStatus.mockResolvedValue({
      generated_at: "2026-09-30T12:00:00.000Z",
      paused: ["session_observe"],
      workers: {},
      backlog: {
        session_observe_pending: 4,
        memory_dirty_conversations: 0,
        embed_pending: null,
      },
      stats: {},
      totals_24h: {
        calls: 12,
        errors: 1,
        prompt_tokens: 100,
        completion_tokens: 50,
        cost: null,
      },
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("loads status summary and opens flow on button click", async () => {
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(<BackgroundSettingsTab onOpenBackgroundFlow={onOpen} />);
    await waitFor(() => {
      expect(screen.getByText("12")).toBeInTheDocument();
    });
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("会话记忆抽取")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "打开后台流程图" }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});

describe("settings tabs", () => {
  it("includes background tab before usage", () => {
    const ids = SETTINGS_TABS.map((t) => t.id);
    const bgIdx = ids.indexOf("background");
    const usageIdx = ids.indexOf("usage");
    expect(bgIdx).toBeGreaterThan(-1);
    expect(bgIdx).toBeLessThan(usageIdx);
    expect(SETTINGS_TABS.find((t) => t.id === "background")?.label).toBe("后台");
  });
});
