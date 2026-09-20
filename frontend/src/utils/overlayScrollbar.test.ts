import { afterEach, describe, expect, it, vi } from "vitest";
import {
  findScrollableAncestor,
  initOverlayScrollbar,
  intersectBoxes,
  overlayPageJump,
  overlayScrollerViewport,
  overlayThumbLayout,
  resetOverlayScrollbarForTests,
  resolveScrollTarget,
  scrollPosFromThumbOffset,
} from "./overlayScrollbar";

describe("overlayThumbLayout", () => {
  it("returns null when content fits", () => {
    expect(overlayThumbLayout(400, 400, 0, 400)).toBeNull();
    expect(overlayThumbLayout(399, 400, 0, 400)).toBeNull();
  });

  it("sizes the thumb by the visible ratio and pins it at the ends", () => {
    const mid = overlayThumbLayout(1000, 200, 400, 200, 32);
    expect(mid).not.toBeNull();
    expect(mid!.thumbSize).toBe(40);
    expect(mid!.thumbOffset).toBeCloseTo(80);

    const start = overlayThumbLayout(1000, 200, 0, 200, 32);
    expect(start!.thumbOffset).toBe(0);

    const end = overlayThumbLayout(1000, 200, 800, 200, 32);
    expect(end!.thumbOffset).toBeCloseTo(160);
  });

  it("enforces a minimum thumb so the grab target stays hittable", () => {
    const layout = overlayThumbLayout(10000, 100, 0, 100, 32);
    expect(layout!.thumbSize).toBe(32);
  });
});

describe("scrollPosFromThumbOffset", () => {
  it("maps thumb travel back onto the overflow range", () => {
    expect(scrollPosFromThumbOffset(80, 40, 200, 1000, 200)).toBeCloseTo(400);
    expect(scrollPosFromThumbOffset(0, 40, 200, 1000, 200)).toBe(0);
    expect(scrollPosFromThumbOffset(160, 40, 200, 1000, 200)).toBeCloseTo(800);
  });
});

describe("overlayPageJump", () => {
  it("pages away from the thumb and ignores clicks on the thumb", () => {
    expect(overlayPageJump(10, 80, 40, 200, 400, 800)).toBeCloseTo(220);
    expect(overlayPageJump(180, 80, 40, 200, 400, 800)).toBeCloseTo(580);
    expect(overlayPageJump(90, 80, 40, 200, 400, 800)).toBe(400);
  });

  it("clamps to the overflow range", () => {
    expect(overlayPageJump(10, 20, 40, 200, 50, 800)).toBe(0);
    expect(overlayPageJump(180, 20, 40, 200, 700, 800)).toBe(800);
  });
});

describe("intersectBoxes", () => {
  it("returns the overlap or null when too small", () => {
    expect(
      intersectBoxes(
        { top: 0, left: 0, right: 100, bottom: 100 },
        { top: 50, left: 50, right: 150, bottom: 150 },
      ),
    ).toEqual({ top: 50, left: 50, right: 100, bottom: 100 });
    expect(
      intersectBoxes(
        { top: 0, left: 0, right: 10, bottom: 10 },
        { top: 9, left: 9, right: 20, bottom: 20 },
      ),
    ).toBeNull();
  });
});

describe("resolveScrollTarget", () => {
  it("uses the document element for document-level scroll", () => {
    expect(resolveScrollTarget(document)).toBe(document.documentElement);
  });
});

describe("overlayScrollerViewport", () => {
  it("does not let html/body overflow:hidden collapse the scroller box", () => {
    vi.stubGlobal("innerWidth", 800);
    vi.stubGlobal("innerHeight", 600);
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
    const el = document.createElement("div");
    el.style.overflowY = "auto";
    el.getBoundingClientRect = () =>
      ({
        top: 10,
        left: 20,
        right: 420,
        bottom: 410,
        width: 400,
        height: 400,
        x: 20,
        y: 10,
        toJSON() {
          return {};
        },
      }) as DOMRect;
    document.body.appendChild(el);
    expect(overlayScrollerViewport(el)).toEqual({
      top: 10,
      left: 20,
      right: 420,
      bottom: 410,
    });
    el.remove();
    document.documentElement.style.overflow = "";
    document.body.style.overflow = "";
  });
});

describe("findScrollableAncestor", () => {
  it("walks from inner text to the overflow panel", () => {
    const scroller = document.createElement("div");
    scroller.style.overflowY = "auto";
    Object.defineProperty(scroller, "scrollHeight", { value: 800, configurable: true });
    Object.defineProperty(scroller, "clientHeight", { value: 200, configurable: true });
    const inner = document.createElement("p");
    scroller.appendChild(inner);
    document.body.appendChild(scroller);
    expect(findScrollableAncestor(inner)).toBe(scroller);
    scroller.remove();
  });
});

describe("initOverlayScrollbar", () => {
  afterEach(() => {
    resetOverlayScrollbarForTests();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("shows a vertical rail after a scrollable panel scrolls", () => {
    vi.stubGlobal("innerWidth", 800);
    vi.stubGlobal("innerHeight", 600);
    initOverlayScrollbar();

    const scroller = document.createElement("div");
    scroller.style.overflowY = "auto";
    Object.defineProperty(scroller, "scrollHeight", { value: 2000, configurable: true });
    Object.defineProperty(scroller, "clientHeight", { value: 400, configurable: true });
    Object.defineProperty(scroller, "scrollTop", { value: 200, writable: true, configurable: true });
    Object.defineProperty(scroller, "scrollWidth", { value: 400, configurable: true });
    Object.defineProperty(scroller, "clientWidth", { value: 400, configurable: true });
    scroller.getBoundingClientRect = () =>
      ({
        top: 40,
        left: 80,
        right: 480,
        bottom: 440,
        width: 400,
        height: 400,
        x: 80,
        y: 40,
        toJSON() {
          return {};
        },
      }) as DOMRect;
    document.body.appendChild(scroller);
    scroller.dispatchEvent(new Event("scroll", { bubbles: false }));

    const rail = document.querySelector(".lore-scroll-rail--y");
    expect(rail).toBeTruthy();
    expect(rail?.classList.contains("is-visible")).toBe(true);
    const thumb = rail?.querySelector(".lore-scroll-thumb") as HTMLElement;
    expect(Number.parseFloat(thumb.style.height)).toBeGreaterThan(30);

    scroller.remove();
  });

  it("pages when clicking the track above the thumb", () => {
    vi.stubGlobal("innerWidth", 800);
    vi.stubGlobal("innerHeight", 600);
    initOverlayScrollbar();

    const scroller = document.createElement("div");
    scroller.style.overflowY = "auto";
    let scrollTop = 400;
    Object.defineProperty(scroller, "scrollHeight", { value: 2000, configurable: true });
    Object.defineProperty(scroller, "clientHeight", { value: 400, configurable: true });
    Object.defineProperty(scroller, "scrollTop", {
      get: () => scrollTop,
      set: (v: number) => {
        scrollTop = v;
      },
      configurable: true,
    });
    Object.defineProperty(scroller, "scrollWidth", { value: 400, configurable: true });
    Object.defineProperty(scroller, "clientWidth", { value: 400, configurable: true });
    scroller.getBoundingClientRect = () =>
      ({
        top: 0,
        left: 0,
        right: 400,
        bottom: 400,
        width: 400,
        height: 400,
        x: 0,
        y: 0,
        toJSON() {
          return {};
        },
      }) as DOMRect;
    document.body.appendChild(scroller);
    scroller.dispatchEvent(new Event("scroll", { bubbles: false }));

    const rail = document.querySelector(".lore-scroll-rail--y") as HTMLElement;
    rail.getBoundingClientRect = () =>
      ({
        top: 2,
        left: 389,
        right: 400,
        bottom: 398,
        width: 11,
        height: 396,
        x: 389,
        y: 2,
        toJSON() {
          return {};
        },
      }) as DOMRect;
    rail.dispatchEvent(
      new PointerEvent("pointerdown", { clientX: 394, clientY: 20, bubbles: true }),
    );
    expect(scrollTop).toBeLessThan(400);

    scroller.remove();
  });

  it("shows the rail when wheeling over inner content", () => {
    vi.stubGlobal("innerWidth", 800);
    vi.stubGlobal("innerHeight", 600);
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0);
      return 0;
    });
    initOverlayScrollbar();

    const scroller = document.createElement("div");
    scroller.style.overflowY = "auto";
    Object.defineProperty(scroller, "scrollHeight", { value: 2000, configurable: true });
    Object.defineProperty(scroller, "clientHeight", { value: 400, configurable: true });
    Object.defineProperty(scroller, "scrollTop", { value: 80, writable: true, configurable: true });
    Object.defineProperty(scroller, "scrollWidth", { value: 400, configurable: true });
    Object.defineProperty(scroller, "clientWidth", { value: 400, configurable: true });
    scroller.getBoundingClientRect = () =>
      ({
        top: 0,
        left: 0,
        right: 400,
        bottom: 400,
        width: 400,
        height: 400,
        x: 0,
        y: 0,
        toJSON() {
          return {};
        },
      }) as DOMRect;
    const inner = document.createElement("p");
    inner.textContent = "inner";
    scroller.appendChild(inner);
    document.body.appendChild(scroller);
    inner.dispatchEvent(new WheelEvent("wheel", { deltaY: 80, bubbles: true }));

    const rail = document.querySelector(".lore-scroll-rail--y");
    expect(rail?.classList.contains("is-visible")).toBe(true);
    scroller.remove();
  });
});
