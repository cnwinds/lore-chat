import { describe, expect, it } from "vitest";
import { scrollTopForLine, visibleLinesOf } from "./geometry";

describe("merge3 滚动几何", () => {
  it("行 → 滚动位置单调不减且不越界", () => {
    for (const height of [400, 600, 781]) {
      let prev = -Infinity;
      for (let line = 0; line < 400; line++) {
        const top = scrollTopForLine(line, height);
        expect(top).toBeGreaterThanOrEqual(0);
        expect(top).toBeGreaterThanOrEqual(prev);
        prev = top;
      }
    }
  });

  it("可见行数至少为 1", () => {
    expect(visibleLinesOf(0)).toBe(1);
    expect(visibleLinesOf(21)).toBe(1);
    expect(visibleLinesOf(840)).toBe(40);
  });
});
