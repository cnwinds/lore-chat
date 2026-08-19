import { describe, expect, it } from "vitest";
import { areTourAnchorsReady, shouldShowTour, TOUR_STEPS } from "./demoTour";

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

  it("演示访客每次刷新都展示", () => {
    expect(shouldShowTour(true)).toBe(true);
    expect(shouldShowTour(false)).toBe(false);
  });

  it("三步锚点都有尺寸才算就绪", () => {
    const root = document.createElement("div");
    expect(areTourAnchorsReady(root)).toBe(false);

    for (const step of TOUR_STEPS) {
      const el = document.createElement("div");
      el.setAttribute("data-demo-anchor", step.anchor);
      el.getBoundingClientRect = () =>
        ({
          width: 40,
          height: 20,
          top: 0,
          left: 0,
          bottom: 20,
          right: 40,
          x: 0,
          y: 0,
          toJSON: () => ({}),
        }) as DOMRect;
      root.appendChild(el);
    }
    expect(areTourAnchorsReady(root)).toBe(true);

    const zero = root.querySelector(
      '[data-demo-anchor="composer"]',
    ) as HTMLElement;
    zero.getBoundingClientRect = () =>
      ({
        width: 0,
        height: 0,
        top: 0,
        left: 0,
        bottom: 0,
        right: 0,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }) as DOMRect;
    expect(areTourAnchorsReady(root)).toBe(false);
  });
});
