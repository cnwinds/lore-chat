import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api";
import type { UsageAgg, UsageSummary } from "../../api";
import * as channelPlugins from "../../api/channelPlugins";
import { UsageSettingsTab } from "./UsageSettingsTab";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    getUsageSummary: vi.fn(),
    getUsageEvents: vi.fn(),
    getUsagePrefs: vi.fn(),
    getUsagePrices: vi.fn(),
    getSettings: vi.fn(),
    clearUsage: vi.fn(),
    putUsagePrefs: vi.fn(),
    putUsagePrice: vi.fn(),
  };
});

vi.mock("../../api/channelPlugins", () => ({
  listChannelInstances: vi.fn(),
}));

const getUsageSummary = vi.mocked(api.getUsageSummary);
const getUsageEvents = vi.mocked(api.getUsageEvents);
const getUsagePrefs = vi.mocked(api.getUsagePrefs);
const getUsagePrices = vi.mocked(api.getUsagePrices);
const getSettings = vi.mocked(api.getSettings);
const listChannelInstances = vi.mocked(channelPlugins.listChannelInstances);

function agg(partial: Partial<UsageAgg> & { bucket?: string; model?: string }): UsageAgg {
  return {
    calls: 0,
    ok_calls: 0,
    error_calls: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    total_tokens: 0,
    unknown_token_calls: 0,
    cost: 0,
    cost_known_calls: 0,
    unpriced_calls: 0,
    ...partial,
  };
}

function summary(): UsageSummary {
  return {
    timezone: "Asia/Shanghai",
    granularity: "day",
    start: "2026-09-01T00:00:00+08:00",
    end: "2026-09-21T00:00:00+08:00",
    totals: agg({ calls: 12, total_tokens: 158, cost: 0.01, cost_known_calls: 1 }),
    by_bucket: [
      agg({ bucket: "2026-09-01", calls: 1, total_tokens: 8 }),
      agg({ bucket: "2026-09-02", calls: 0, total_tokens: 0 }),
      agg({ bucket: "2026-09-18", calls: 4, total_tokens: 100 }),
      agg({ bucket: "2026-09-20", calls: 0, total_tokens: 0 }),
    ],
    by_model: [
      { ...agg({ calls: 2, total_tokens: 10, prompt_tokens: 10 }), model: "alpha-low" },
      { ...agg({ calls: 3, total_tokens: 100, prompt_tokens: 60, completion_tokens: 40 }), model: "beta-high" },
      { ...agg({ calls: 1, total_tokens: 50, prompt_tokens: 50 }), model: "mid" },
    ],
  };
}

async function renderTab() {
  render(<UsageSettingsTab />);
  await waitFor(() => {
    expect(screen.getByRole("listbox", { name: /用量趋势/ })).toBeInTheDocument();
  });
}

describe("UsageSettingsTab chart and model order", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    getUsageSummary.mockResolvedValue(summary());
    getUsageEvents.mockResolvedValue({ items: [], limit: 40, offset: 0 });
    getUsagePrefs.mockResolvedValue({ timezone: "Asia/Shanghai", retention_days: 365 });
    getUsagePrices.mockResolvedValue({ items: [] });
    getSettings.mockResolvedValue({});
    listChannelInstances.mockResolvedValue({ instances: [] });
  });

  it("reads the current bar above the chart instead of labeling every column", async () => {
    const user = userEvent.setup();
    await renderTab();

    const readout = document.querySelector(".usage-trend-readout") as HTMLElement;
    expect(readout).toHaveTextContent("9月18日");
    expect(readout).toHaveTextContent("100 tokens");
    expect(readout).toHaveTextContent("4 次");

    const axis = document.querySelector(".usage-trend-axis") as HTMLElement;
    expect(axis).toHaveTextContent("9月1日");
    expect(axis).toHaveTextContent("9月20日");
    expect(screen.queryByText("09-01")).not.toBeInTheDocument();
    expect(screen.queryByText("条长度表示相对 Token 占比")).not.toBeInTheDocument();

    await user.hover(screen.getByRole("option", { name: /9月1日/ }));
    expect(readout).toHaveTextContent("9月1日");
    expect(readout).toHaveTextContent("8 tokens");

    const chart = screen.getByRole("listbox", { name: /用量趋势/ });
    chart.focus();
    await user.keyboard("{End}");
    expect(readout).toHaveTextContent("9月20日");
    expect(readout).toHaveTextContent("0 tokens");
  });

  it("lists models from most tokens to least even if the API is alphabetical", async () => {
    await renderTab();
    const names = [...document.querySelectorAll(".usage-model-list .usage-model-name")].map(
      (el) => el.textContent?.trim(),
    );
    expect(names).toEqual(["beta-high", "mid", "alpha-low"]);
  });
});
