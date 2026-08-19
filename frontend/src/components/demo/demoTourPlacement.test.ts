import { describe, expect, it } from "vitest";
import { computeTourCardLayout } from "./demoTourPlacement";

describe("computeTourCardLayout", () => {
  const card = { cardW: 300, cardH: 160, viewportW: 1200, viewportH: 800 };

  it("侧栏高亮时卡片优先放右侧，尖角朝左", () => {
    const layout = computeTourCardLayout(
      { top: 120, left: 16, width: 220, height: 280 },
      card,
    );
    expect(layout.placement).toBe("right");
    expect(layout.left).toBeGreaterThan(16 + 220);
  });

  it("底部输入区高亮时卡片优先放上方", () => {
    const layout = computeTourCardLayout(
      { top: 620, left: 400, width: 480, height: 140 },
      card,
    );
    expect(layout.placement).toBe("top");
    expect(layout.top + card.cardH).toBeLessThanOrEqual(620);
  });

  it("尖角偏移落在卡片边内", () => {
    const layout = computeTourCardLayout(
      { top: 120, left: 16, width: 220, height: 80 },
      card,
    );
    expect(layout.arrowOffset).toBeGreaterThanOrEqual(18);
    expect(layout.arrowOffset).toBeLessThanOrEqual(card.cardH - 18);
  });
});
