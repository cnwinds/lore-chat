export const LEFT_SIDEBAR_MIN = 64;
export const LEFT_SIDEBAR_MAX = 420;
export const LEFT_SIDEBAR_DEFAULT = 272;
export const LEFT_SIDEBAR_ICON_AT = 88;
export const LEFT_SIDEBAR_WIDTH_KEY = "lorechat.leftSidebarWidth";

export function clampLeftSidebarWidth(n: number): number {
  if (!Number.isFinite(n)) return LEFT_SIDEBAR_DEFAULT;
  return Math.min(LEFT_SIDEBAR_MAX, Math.max(LEFT_SIDEBAR_MIN, Math.round(n)));
}

export function isLeftSidebarIconOnly(width: number): boolean {
  return width <= LEFT_SIDEBAR_ICON_AT;
}

export function readLeftSidebarWidth(): number {
  try {
    const raw = localStorage.getItem(LEFT_SIDEBAR_WIDTH_KEY);
    if (!raw) return LEFT_SIDEBAR_DEFAULT;
    return clampLeftSidebarWidth(Number(raw));
  } catch {
    return LEFT_SIDEBAR_DEFAULT;
  }
}

export function persistLeftSidebarWidth(width: number): void {
  try {
    localStorage.setItem(LEFT_SIDEBAR_WIDTH_KEY, String(clampLeftSidebarWidth(width)));
  } catch {
    /* ignore */
  }
}
