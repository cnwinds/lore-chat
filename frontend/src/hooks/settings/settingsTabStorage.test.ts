import { afterEach, describe, expect, it } from "vitest";
import {
  SETTINGS_TABS,
  readStoredSettingsTab,
  writeStoredSettingsTab,
} from "./settingsTabStorage";

afterEach(() => {
  localStorage.clear();
});

describe("settingsTabStorage", () => {
  it("does not list 聊天通道 among settings tabs", () => {
    expect(SETTINGS_TABS.map((tab) => tab.id)).not.toContain("openapi");
    expect(SETTINGS_TABS.map((tab) => tab.label)).not.toContain("聊天通道");
  });

  it("falls back when an old openapi tab is still stored", () => {
    localStorage.setItem("lorechat.settingsTab", "openapi");
    expect(readStoredSettingsTab()).toBe("model");
  });

  it("round-trips a remaining settings tab", () => {
    writeStoredSettingsTab("account");
    expect(readStoredSettingsTab()).toBe("account");
  });
});
