import { describe, expect, it } from "vitest";
import {
  bucketLabel,
  defaultTrendIndex,
  sortModelsByUsage,
  stepTrendIndex,
  trendAxisEnds,
} from "./usageChart";

describe("bucketLabel", () => {
  it("formats hour / day / week / month in readable Chinese", () => {
    expect(bucketLabel("2026-09-20 14:00", "hour")).toBe("9月20日 14时");
    expect(bucketLabel("2026-09-01", "day")).toBe("9月1日");
    expect(bucketLabel("2026-W32", "week")).toBe("2026年第32周");
    expect(bucketLabel("2026-09", "month")).toBe("2026年9月");
  });
});

describe("sortModelsByUsage", () => {
  it("orders by tokens, then calls, then name", () => {
    const rows = sortModelsByUsage([
      { model: "b-low", total_tokens: 10, calls: 9 },
      { model: "a-high", total_tokens: 100, calls: 1 },
      { model: "c-mid", total_tokens: 10, calls: 2 },
    ]);
    expect(rows.map((r) => r.model)).toEqual(["a-high", "b-low", "c-mid"]);
  });
});

describe("defaultTrendIndex", () => {
  it("picks the last bucket that has usage", () => {
    expect(
      defaultTrendIndex([
        { total_tokens: 8, calls: 1 },
        { total_tokens: 0, calls: 0 },
        { total_tokens: 0, calls: 0 },
      ]),
    ).toBe(0);
    expect(
      defaultTrendIndex([
        { total_tokens: 1 },
        { total_tokens: 9 },
        { total_tokens: 0 },
      ]),
    ).toBe(1);
    expect(defaultTrendIndex([{ total_tokens: 0 }, { total_tokens: 0 }])).toBe(1);
  });
});

describe("trendAxisEnds", () => {
  it("returns readable start and end labels", () => {
    expect(
      trendAxisEnds(
        [{ bucket: "2026-09-01" }, { bucket: "2026-09-20" }],
        "day",
      ),
    ).toEqual({ start: "9月1日", end: "9月20日" });
    expect(trendAxisEnds([], "day")).toBeNull();
  });
});

describe("stepTrendIndex", () => {
  it("clamps at both ends", () => {
    expect(stepTrendIndex(0, -1, 4)).toBe(0);
    expect(stepTrendIndex(3, 1, 4)).toBe(3);
    expect(stepTrendIndex(1, 1, 4)).toBe(2);
    expect(stepTrendIndex(0, 1, 0)).toBe(0);
  });
});
