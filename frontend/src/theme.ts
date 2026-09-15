export const THEME_IDS = ["celadon", "ink", "iris", "beige"] as const;

export type Theme = (typeof THEME_IDS)[number];
export type ThemeTone = "light" | "dark";

export type ThemeMeta = {
  label: string;
  tone: ThemeTone;
  /** [底色, 强调色]，用于菜单色票 */
  swatches: readonly [string, string];
};

export const THEME_CATALOG: Record<Theme, ThemeMeta> = {
  celadon: { label: "青瓷", tone: "light", swatches: ["#e7eeea", "#c44536"] },
  ink: { label: "墨砚", tone: "dark", swatches: ["#101614", "#e07064"] },
  iris: { label: "紫藤", tone: "light", swatches: ["#f3f4f6", "#5b5bd6"] },
  beige: { label: "米色", tone: "light", swatches: ["#ede4d2", "#7a3e2b"] },
};

export const STORAGE_KEY = "kb-theme";
export const THEME_CHANGE_EVENT = "kb-theme-change";

const THEME_ID_SET = new Set<string>(THEME_IDS);

export function isTheme(value: string | null | undefined): value is Theme {
  return !!value && THEME_ID_SET.has(value);
}

/** 旧版只存 light/dark；分别迁到青瓷 / 墨砚。 */
export function normalizeTheme(raw: string | null | undefined): Theme {
  if (raw === "light") return "celadon";
  if (raw === "dark") return "ink";
  if (isTheme(raw)) return raw;
  return "celadon";
}

export function getStoredTheme(): Theme {
  try {
    return normalizeTheme(localStorage.getItem(STORAGE_KEY));
  } catch {
    return "celadon";
  }
}

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.dataset.themeTone = THEME_CATALOG[theme].tone;
}

function persistTheme(theme: Theme) {
  try {
    if (localStorage.getItem(STORAGE_KEY) !== theme) {
      localStorage.setItem(STORAGE_KEY, theme);
    }
  } catch {
    /* ignore */
  }
}

export function initTheme() {
  const theme = getStoredTheme();
  persistTheme(theme);
  applyTheme(theme);
}

export function setTheme(theme: Theme) {
  persistTheme(theme);
  applyTheme(theme);
  window.dispatchEvent(new CustomEvent(THEME_CHANGE_EVENT, { detail: theme }));
}

export function subscribeThemeChange(handler: (theme: Theme) => void): () => void {
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) handler(normalizeTheme(e.newValue));
  };
  const onLocal = (e: Event) => {
    handler(normalizeTheme((e as CustomEvent<string>).detail));
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(THEME_CHANGE_EVENT, onLocal);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(THEME_CHANGE_EVENT, onLocal);
  };
}
