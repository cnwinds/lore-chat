import { afterEach, describe, expect, it } from "vitest";
import {
  STORAGE_KEY,
  THEME_CATALOG,
  applyTheme,
  getStoredTheme,
  initTheme,
  normalizeTheme,
  setTheme,
} from "./theme";

afterEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  delete document.documentElement.dataset.themeTone;
});

describe("normalizeTheme", () => {
  it("migrates legacy light/dark to celadon/ink", () => {
    expect(normalizeTheme("light")).toBe("celadon");
    expect(normalizeTheme("dark")).toBe("ink");
  });

  it("keeps known palettes", () => {
    expect(normalizeTheme("celadon")).toBe("celadon");
    expect(normalizeTheme("ink")).toBe("ink");
    expect(normalizeTheme("iris")).toBe("iris");
    expect(normalizeTheme("beige")).toBe("beige");
  });

  it("falls back to celadon for empty or unknown values", () => {
    expect(normalizeTheme(null)).toBe("celadon");
    expect(normalizeTheme("")).toBe("celadon");
    expect(normalizeTheme("purple")).toBe("celadon");
  });
});

describe("theme persistence", () => {
  it("reads migrated values from storage", () => {
    localStorage.setItem(STORAGE_KEY, "light");
    expect(getStoredTheme()).toBe("celadon");
    localStorage.setItem(STORAGE_KEY, "dark");
    expect(getStoredTheme()).toBe("ink");
  });

  it("rewrites legacy keys on init", () => {
    localStorage.setItem(STORAGE_KEY, "light");
    initTheme();
    expect(localStorage.getItem(STORAGE_KEY)).toBe("celadon");
    expect(document.documentElement.dataset.theme).toBe("celadon");
    expect(document.documentElement.dataset.themeTone).toBe("light");
  });

  it("applies tone for ink", () => {
    applyTheme("ink");
    expect(document.documentElement.dataset.theme).toBe("ink");
    expect(document.documentElement.dataset.themeTone).toBe("dark");
  });

  it("persists a chosen palette and notifies listeners", () => {
    const seen: string[] = [];
    const onChange = (e: Event) => {
      seen.push((e as CustomEvent<string>).detail);
    };
    window.addEventListener("kb-theme-change", onChange);
    setTheme("beige");
    window.removeEventListener("kb-theme-change", onChange);
    expect(localStorage.getItem(STORAGE_KEY)).toBe("beige");
    expect(document.documentElement.dataset.theme).toBe("beige");
    expect(document.documentElement.dataset.themeTone).toBe(
      THEME_CATALOG.beige.tone,
    );
    expect(seen).toEqual(["beige"]);
  });
});
