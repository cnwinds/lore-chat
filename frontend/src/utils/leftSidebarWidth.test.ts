import { afterEach, describe, expect, it } from "vitest";
import {
  LEFT_SIDEBAR_DEFAULT,
  LEFT_SIDEBAR_MAX,
  LEFT_SIDEBAR_MIN,
  LEFT_SIDEBAR_ROLE_SHARE_DEFAULT,
  LEFT_SIDEBAR_ROLE_SHARE_KEY,
  LEFT_SIDEBAR_WIDTH_KEY,
  clampLeftSidebarRoleShare,
  clampLeftSidebarWidth,
  isLeftSidebarIconOnly,
  persistLeftSidebarRoleShare,
  persistLeftSidebarWidth,
  readLeftSidebarRoleShare,
  readLeftSidebarWidth,
  shouldUseLeftSidebarIcons,
} from "./leftSidebarWidth";

afterEach(() => {
  localStorage.removeItem(LEFT_SIDEBAR_WIDTH_KEY);
  localStorage.removeItem(LEFT_SIDEBAR_ROLE_SHARE_KEY);
});

describe("clampLeftSidebarWidth", () => {
  it("clamps to the icon rail and max width", () => {
    expect(clampLeftSidebarWidth(10)).toBe(LEFT_SIDEBAR_MIN);
    expect(clampLeftSidebarWidth(800)).toBe(LEFT_SIDEBAR_MAX);
    expect(clampLeftSidebarWidth(200)).toBe(200);
  });
});

describe("isLeftSidebarIconOnly", () => {
  it("is icon-only at or below the threshold", () => {
    expect(isLeftSidebarIconOnly(64)).toBe(true);
    expect(isLeftSidebarIconOnly(88)).toBe(true);
    expect(isLeftSidebarIconOnly(120)).toBe(false);
  });
});

describe("shouldUseLeftSidebarIcons", () => {
  it("never icon-collapses the mobile drawer", () => {
    expect(shouldUseLeftSidebarIcons(64, true)).toBe(false);
    expect(shouldUseLeftSidebarIcons(88, true)).toBe(false);
    expect(shouldUseLeftSidebarIcons(272, true)).toBe(false);
  });

  it("still icon-collapses a narrow desktop rail", () => {
    expect(shouldUseLeftSidebarIcons(64, false)).toBe(true);
    expect(shouldUseLeftSidebarIcons(120, false)).toBe(false);
  });
});

describe("readLeftSidebarWidth", () => {
  it("falls back to default and persists a clamped value", () => {
    expect(readLeftSidebarWidth()).toBe(LEFT_SIDEBAR_DEFAULT);
    persistLeftSidebarWidth(48);
    expect(readLeftSidebarWidth()).toBe(LEFT_SIDEBAR_MIN);
  });
});

describe("left sidebar role/kb split", () => {
  it("clamps the role share and remembers it", () => {
    expect(readLeftSidebarRoleShare()).toBe(LEFT_SIDEBAR_ROLE_SHARE_DEFAULT);
    expect(clampLeftSidebarRoleShare(0.05)).toBe(0.22);
    expect(clampLeftSidebarRoleShare(0.95)).toBe(0.78);
    persistLeftSidebarRoleShare(0.6);
    expect(readLeftSidebarRoleShare()).toBe(0.6);
  });
});
