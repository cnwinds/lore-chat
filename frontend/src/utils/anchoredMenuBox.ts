export type Rect = {
  top: number;
  bottom: number;
  left: number;
  right: number;
};

export type Size = { width: number; height: number };

/** 相对锚点放置菜单：下方空间够则向下，否则向上；水平按 start/end 对齐并夹入视口。 */
export function anchoredMenuBox(
  anchor: Rect,
  menu: Size,
  viewport: Size,
  opts?: { align?: "start" | "end"; gap?: number; pad?: number },
): { top: number; left: number } {
  const gap = opts?.gap ?? 4;
  const pad = opts?.pad ?? 8;
  const align = opts?.align ?? "end";
  const spaceBelow = viewport.height - anchor.bottom - gap;
  const spaceAbove = anchor.top - gap - pad;
  const openDown = spaceBelow >= menu.height || spaceBelow >= spaceAbove;
  const top = openDown
    ? anchor.bottom + gap
    : Math.max(pad, anchor.top - gap - menu.height);
  const rawLeft = align === "end" ? anchor.right - menu.width : anchor.left;
  const maxLeft = Math.max(pad, viewport.width - menu.width - pad);
  const left = Math.min(Math.max(pad, rawLeft), maxLeft);
  return { top, left };
}
