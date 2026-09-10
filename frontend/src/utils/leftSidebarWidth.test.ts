import { afterEach, describe, expect, it } from "vitest";
import {
  LEFT_SIDEBAR_DEFAULT,
  LEFT_SIDEBAR_MAX,
  LEFT_SIDEBAR_MIN,
  LEFT_SIDEBAR_WIDTH_KEY,
  clampLeftSidebarWidth,
  isLeftSidebarIconOnly,
  persistLeftSidebarWidth,
  readLeftSidebarWidth,
} from "./leftSidebarWidth";

afterEach(() => {
  localStorage.removeItem(LEFT_SIDEBAR_WIDTH_KEY);
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

describe("readLeftSidebarWidth", () => {
  it("falls back to default and persists a clamped value", () => {
    expect(readLeftSidebarWidth()).toBe(LEFT_SIDEBAR_DEFAULT);
    persistLeftSidebarWidth(48);
    expect(readLeftSidebarWidth()).toBe(LEFT_SIDEBAR_MIN);
  });
});
