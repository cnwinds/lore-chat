import { describe, expect, it } from "vitest";
import {
  centerLineOf,
  scrollTopForLine,
  visibleLinesOf,
} from "./geometry";

describe("merge3 滚动几何", () => {
  const heights = [400, 600, 781];

  it("写读严格互逆：对齐后反查中心行不漂移", () => {
    for (const height of heights) {
      const v = visibleLinesOf(height);
      // 顶部/底部钳制区无法居中，互逆只在非钳制区间成立
      for (let line = Math.ceil(v / 2); line < 400; line++) {
        const top = scrollTopForLine(line, height);
        expect(centerLineOf(top, height)).toBe(line);
      }
    }
  });

  it("滚动位置单调不减", () => {
    for (const height of heights) {
      let prev = -Infinity;
      for (let line = 0; line < 400; line++) {
        const top = scrollTopForLine(line, height);
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
