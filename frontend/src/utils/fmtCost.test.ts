import { describe, expect, it } from "vitest";
import { fmtCost } from "./fmtCost";

describe("fmtCost", () => {
  it("formats without currency symbol", () => {
    expect(fmtCost(null, true)).toBe("—");
    expect(fmtCost(0.005, true)).toBe("0.005000");
    expect(fmtCost(0.08, true)).toBe("0.0800");
    expect(fmtCost(1.23, true)).toBe("1.23");
  });
});
