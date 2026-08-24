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
});
