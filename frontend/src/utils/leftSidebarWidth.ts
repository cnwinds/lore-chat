export const LEFT_SIDEBAR_MIN = 64;
export const LEFT_SIDEBAR_MAX = 420;
export const LEFT_SIDEBAR_DEFAULT = 272;
export const LEFT_SIDEBAR_ICON_AT = 88;
export const LEFT_SIDEBAR_WIDTH_KEY = "lorechat.leftSidebarWidth";
export const LEFT_SIDEBAR_ROLE_SHARE_KEY = "lorechat.leftSidebarRoleShare";
export const LEFT_SIDEBAR_ROLE_SHARE_DEFAULT = 0.46;
export const LEFT_SIDEBAR_ROLE_SHARE_MIN = 0.22;
export const LEFT_SIDEBAR_ROLE_SHARE_MAX = 0.78;
export const LEFT_SIDEBAR_SPLIT_MIN_PX = 120;

export function clampLeftSidebarWidth(n: number): number {
  if (!Number.isFinite(n)) return LEFT_SIDEBAR_DEFAULT;
  return Math.min(LEFT_SIDEBAR_MAX, Math.max(LEFT_SIDEBAR_MIN, Math.round(n)));
}

export function isLeftSidebarIconOnly(width: number): boolean {
  return width <= LEFT_SIDEBAR_ICON_AT;
}

/**
 * 桌面左栏拖到 ≤88px 才进图标轨。手机抽屉 CSS 宽度是 min(300px, 88vw)，
 * 与 localStorage 里的桌面栏宽无关；绝不能因为桌面曾经拖窄就把手机侧栏
 * 藏掉角色名 / 目录名 / 底栏文字。
 */
export function shouldUseLeftSidebarIcons(
  width: number,
  mobileLayout = false,
): boolean {
  return !mobileLayout && isLeftSidebarIconOnly(width);
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

export function clampLeftSidebarRoleShare(
  share: number,
  containerHeight = 0,
): number {
  if (!Number.isFinite(share)) return LEFT_SIDEBAR_ROLE_SHARE_DEFAULT;
  let min = LEFT_SIDEBAR_ROLE_SHARE_MIN;
  let max = LEFT_SIDEBAR_ROLE_SHARE_MAX;
  if (containerHeight > LEFT_SIDEBAR_SPLIT_MIN_PX * 2) {
    const edge = LEFT_SIDEBAR_SPLIT_MIN_PX / containerHeight;
    min = Math.max(min, edge);
    max = Math.min(max, 1 - edge);
  }
  return Math.min(max, Math.max(min, share));
}

export function readLeftSidebarRoleShare(): number {
  try {
    const raw = localStorage.getItem(LEFT_SIDEBAR_ROLE_SHARE_KEY);
    if (!raw) return LEFT_SIDEBAR_ROLE_SHARE_DEFAULT;
    return clampLeftSidebarRoleShare(Number(raw));
  } catch {
    return LEFT_SIDEBAR_ROLE_SHARE_DEFAULT;
  }
}

export function persistLeftSidebarRoleShare(share: number): void {
  try {
    localStorage.setItem(
      LEFT_SIDEBAR_ROLE_SHARE_KEY,
      String(clampLeftSidebarRoleShare(share)),
    );
  } catch {
    /* ignore */
  }
}
