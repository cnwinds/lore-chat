import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api";
import { BackgroundFlowModal } from "./BackgroundFlowModal";
import { mockBackgroundOverview } from "./mockOverview";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    getBackgroundOverview: vi.fn(),
    getBackgroundStatus: vi.fn(),
    putSettings: vi.fn(),
    listBackgroundCalls: vi.fn(),
    getBackgroundCall: vi.fn(),
  };
});

vi.mock("../../utils/toast", () => ({
  showToast: vi.fn(),
}));

const getBackgroundOverview = vi.mocked(api.getBackgroundOverview);
const getBackgroundStatus = vi.mocked(api.getBackgroundStatus);
const putSettings = vi.mocked(api.putSettings);

describe("BackgroundFlowModal", () => {
  beforeEach(() => {
    getBackgroundOverview.mockReset();
    getBackgroundStatus.mockReset();
    putSettings.mockReset();
    getBackgroundOverview.mockResolvedValue(mockBackgroundOverview);
    getBackgroundStatus.mockResolvedValue(mockBackgroundOverview.status);
    putSettings.mockResolvedValue({});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders grouped lanes and nodes from overview", async () => {
    render(
      <BackgroundFlowModal open onClose={() => {}} onOpenModelSettings={() => {}} />,
    );
    await waitFor(() => {
      expect(screen.getByText("会话定稿观察")).toBeInTheDocument();
    });
    expect(screen.getByText("自动")).toBeInTheDocument();
    expect(screen.getByText("按需")).toBeInTheDocument();
    expect(screen.getByText("主人记忆抽取")).toBeInTheDocument();
    expect(screen.getByText("主人记忆库")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "会话空闲" })).toBeInTheDocument();
    expect(screen.getByText("卡片维护")).toBeInTheDocument();
  });

  it("shows readonly prompt notice when llm node selected", async () => {
    const user = userEvent.setup();
    render(
      <BackgroundFlowModal open onClose={() => {}} onOpenModelSettings={() => {}} />,
    );
    await waitFor(() => {
      expect(screen.getByText("主人记忆抽取")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /主人记忆抽取/ }));
    await user.click(screen.getByRole("tab", { name: "提示词" }));
    expect(
      screen.getByText("提示词由代码维护（AGENTS.md），此处只读。"),
    ).toBeInTheDocument();
    expect(screen.getByText(/注入/)).toBeInTheDocument();
    expect(screen.getByText("{主人名}")).toBeInTheDocument();
  });

  it("sends PUT with background_paused when lane pause toggled", async () => {
    const user = userEvent.setup();
    render(
      <BackgroundFlowModal open onClose={() => {}} onOpenModelSettings={() => {}} />,
    );
    await waitFor(() => {
      expect(screen.getByText("会话定稿观察")).toBeInTheDocument();
    });
    const toggle = screen.getByRole("checkbox", { name: "暂停 会话记忆抽取" });
    await user.click(toggle);
    await waitFor(() => {
      expect(putSettings).toHaveBeenCalledWith({
        background_paused: ["session_observe"],
      });
    });
  });

  it("shows two pause switches on card maintenance lane", async () => {
    render(
      <BackgroundFlowModal open onClose={() => {}} onOpenModelSettings={() => {}} />,
    );
    await waitFor(() => {
      expect(screen.getByText("卡片维护")).toBeInTheDocument();
    });
    expect(screen.getByRole("checkbox", { name: "暂停 整理" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "暂停 人设进化" })).toBeInTheDocument();
  });

  it("toggles persona_evolution pause with correct PUT body", async () => {
    const user = userEvent.setup();
    getBackgroundOverview.mockResolvedValue({
      ...mockBackgroundOverview,
      status: {
        ...mockBackgroundOverview.status,
        paused: ["consolidation"],
      },
    });
    getBackgroundStatus.mockResolvedValue({
      ...mockBackgroundOverview.status,
      paused: ["consolidation"],
    });
    render(
      <BackgroundFlowModal open onClose={() => {}} onOpenModelSettings={() => {}} />,
    );
    await waitFor(() => {
      expect(screen.getByRole("checkbox", { name: "暂停 人设进化" })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("checkbox", { name: "暂停 人设进化" }));
    await waitFor(() => {
      expect(putSettings).toHaveBeenCalledWith({
        background_paused: ["consolidation", "persona_evolution"],
      });
    });
  });

  it("toggles persona_evolution alone when nothing else paused", async () => {
    const user = userEvent.setup();
    render(
      <BackgroundFlowModal open onClose={() => {}} onOpenModelSettings={() => {}} />,
    );
    await waitFor(() => {
      expect(screen.getByRole("checkbox", { name: "暂停 人设进化" })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("checkbox", { name: "暂停 人设进化" }));
    await waitFor(() => {
      expect(putSettings).toHaveBeenCalledWith({
        background_paused: ["persona_evolution"],
      });
    });
  });
});

describe("groupOverviewLanes via UI", () => {
  it("shows link chip on archive node", async () => {
    render(
      <BackgroundFlowModal open onClose={() => {}} onOpenModelSettings={() => {}} />,
    );
    await waitFor(() => {
      expect(screen.getByText("归档合成")).toBeInTheDocument();
    });
    expect(
      screen.getByRole("button", { name: /落库后立即抽取/ }),
    ).toBeInTheDocument();
  });
});
