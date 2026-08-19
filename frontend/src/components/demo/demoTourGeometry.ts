export type HighlightBox = {
  top: number;
  left: number;
  width: number;
  height: number;
};

export const SPOTLIGHT_PAD = 6;

export function measureAnchorBox(
  anchor: string,
  root: ParentNode = document,
): HighlightBox | null {
  const el = root.querySelector(`[data-demo-anchor="${anchor}"]`);
  if (!(el instanceof HTMLElement)) return null;
  const r = el.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) return null;
  return {
    top: r.top - SPOTLIGHT_PAD,
    left: r.left - SPOTLIGHT_PAD,
    width: r.width + SPOTLIGHT_PAD * 2,
    height: r.height + SPOTLIGHT_PAD * 2,
  };
}
