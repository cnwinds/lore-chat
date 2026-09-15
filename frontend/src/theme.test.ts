import { afterEach, describe, expect, it } from "vitest";
import {
  STORAGE_KEY,
  THEME_CATALOG,
  THEME_IDS,
  applyTheme,
  getStoredTheme,
  initTheme,
  normalizeTheme,
  setTheme,
} from "./theme";

function swatchLuminance(hex: string): number {
  const n = Number.parseInt(hex.slice(1), 16);
  const channel = (shift: number) => {
    const c = ((n >> shift) & 255) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(16) + 0.7152 * channel(8) + 0.0722 * channel(0);
}

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
    expect(normalizeTheme("iris")).toBe("iris");
    expect(normalizeTheme("celadon")).toBe("celadon");
    expect(normalizeTheme("beige")).toBe("beige");
    expect(normalizeTheme("ink")).toBe("ink");
    expect(normalizeTheme("violet")).toBe("violet");
  });

  it("falls back to celadon for empty or unknown values", () => {
    expect(normalizeTheme(null)).toBe("celadon");
    expect(normalizeTheme("")).toBe("celadon");
    expect(normalizeTheme("purple")).toBe("celadon");
  });
});

describe("theme catalog", () => {
  it("lists palettes from light to dark", () => {
    expect([...THEME_IDS]).toEqual(["iris", "celadon", "beige", "ink", "violet"]);
    const lums = THEME_IDS.map((id) =>
      swatchLuminance(THEME_CATALOG[id].swatches[0]),
    );
    expect(lums).toEqual([...lums].sort((a, b) => b - a));
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

  it("applies tone for ink and violet", () => {
    applyTheme("ink");
    expect(document.documentElement.dataset.theme).toBe("ink");
    expect(document.documentElement.dataset.themeTone).toBe("dark");
    applyTheme("violet");
    expect(document.documentElement.dataset.theme).toBe("violet");
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
