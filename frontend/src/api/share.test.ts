import { describe, expect, it } from "vitest";
import { ttlSecFromPreset } from "../api/share";

describe("ttlSecFromPreset", () => {
  it("returns null for permanent", () => {
    expect(ttlSecFromPreset("permanent")).toBeNull();
  });

  it("returns seconds for presets", () => {
    expect(ttlSecFromPreset("1d")).toBe(86400);
    expect(ttlSecFromPreset("7d")).toBe(7 * 86400);
  });

  it("returns ttl from custom datetime", () => {
    const future = new Date(Date.now() + 3600 * 1000).toISOString();
    const sec = ttlSecFromPreset("custom", future);
    expect(sec).not.toBeNull();
    expect(sec!).toBeGreaterThanOrEqual(60);
  });
});
