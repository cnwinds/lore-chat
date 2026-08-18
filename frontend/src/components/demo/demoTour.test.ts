import { describe, expect, it } from "vitest";
import { shouldShowTour, TOUR_STEPS } from "./demoTour";

describe("demo tour", () => {
  it("三步，分别指向目录树、高光会话、输入框", () => {
    expect(TOUR_STEPS).toHaveLength(3);
    expect(TOUR_STEPS.map((s) => s.anchor)).toEqual([
      "kb-tree",
      "highlight-conversation",
      "composer",
    ]);
  });

  it("每步都有标题与正文", () => {
    for (const step of TOUR_STEPS) {
      expect(step.title.trim()).not.toBe("");
      expect(step.body.trim()).not.toBe("");
    }
  });

  it("访客首访才展示", () => {
    expect(shouldShowTour(true, null)).toBe(true);
    expect(shouldShowTour(true, "1")).toBe(false);
    expect(shouldShowTour(false, null)).toBe(false);
  });
});
