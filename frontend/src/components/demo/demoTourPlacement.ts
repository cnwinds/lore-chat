import type { HighlightBox } from "./demoTourGeometry";

export type TourCardPlacement = "top" | "bottom" | "left" | "right";

export type TourCardLayout = {
  top: number;
  left: number;
  placement: TourCardPlacement;
  /** 尖角在卡片贴向目标那一边上的偏移（px） */
  arrowOffset: number;
};

function clamp(n: number, min: number, max: number): number {
  if (max < min) return min;
  return Math.min(max, Math.max(min, n));
}

/**
 * 把引导卡片贴在高亮框旁，并给出气泡尖角应朝向的边。
 * placement = 卡片相对高亮的位置（right 表示卡片在高亮右侧，尖角在卡片左边）。
 */
export function computeTourCardLayout(
  highlight: HighlightBox,
  opts: {
    viewportW: number;
    viewportH: number;
    cardW: number;
    cardH: number;
    gap?: number;
    margin?: number;
  },
): TourCardLayout {
  const gap = opts.gap ?? 14;
  const margin = opts.margin ?? 12;
  const { viewportW: vw, viewportH: vh, cardW, cardH } = opts;

  const hx = highlight.left + highlight.width / 2;
  const hy = highlight.top + highlight.height / 2;

  const order: TourCardPlacement[] = (() => {
    if (highlight.top + highlight.height > vh * 0.55) {
      return ["top", "right", "left", "bottom"];
    }
    if (highlight.left + highlight.width < vw * 0.48) {
      return ["right", "bottom", "top", "left"];
    }
    return ["bottom", "top", "left", "right"];
  })();

  type Cand = {
    placement: TourCardPlacement;
    top: number;
    left: number;
    fits: boolean;
  };

  const candidates: Cand[] = order.map((placement) => {
    if (placement === "right") {
      const left = highlight.left + highlight.width + gap;
      const top = clamp(hy - cardH / 2, margin, vh - cardH - margin);
      return {
        placement,
        top,
        left,
        fits: left + cardW <= vw - margin,
      };
    }
    if (placement === "left") {
      const left = highlight.left - gap - cardW;
      const top = clamp(hy - cardH / 2, margin, vh - cardH - margin);
      return {
        placement,
        top,
        left,
        fits: left >= margin,
      };
    }
    if (placement === "bottom") {
      const top = highlight.top + highlight.height + gap;
      const left = clamp(hx - cardW / 2, margin, vw - cardW - margin);
      return {
        placement,
        top,
        left,
        fits: top + cardH <= vh - margin,
      };
    }
    const top = highlight.top - gap - cardH;
    const left = clamp(hx - cardW / 2, margin, vw - cardW - margin);
    return {
      placement: "top",
      top,
      left,
      fits: top >= margin,
    };
  });

  const chosen =
    candidates.find((c) => c.fits) ??
    candidates[0] ?? {
      placement: "bottom" as const,
      top: margin,
      left: margin,
      fits: false,
    };

  const top = clamp(chosen.top, margin, Math.max(margin, vh - cardH - margin));
  const left = clamp(chosen.left, margin, Math.max(margin, vw - cardW - margin));

  const arrowPad = 18;
  let arrowOffset: number;
  if (chosen.placement === "left" || chosen.placement === "right") {
    arrowOffset = clamp(hy - top, arrowPad, Math.max(arrowPad, cardH - arrowPad));
  } else {
    arrowOffset = clamp(hx - left, arrowPad, Math.max(arrowPad, cardW - arrowPad));
  }

  return {
    top,
    left,
    placement: chosen.placement,
    arrowOffset,
  };
}
