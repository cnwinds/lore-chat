import { useEffect, useState } from "react";
import { getStoredTheme, setTheme, type Theme } from "../theme";

export function ThemeToggle() {
  const [theme, setThemeState] = useState<Theme>(() => getStoredTheme());

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === "kb-theme" && (e.newValue === "light" || e.newValue === "dark")) {
        setThemeState(e.newValue);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  function toggle() {
    const next: Theme = theme === "light" ? "dark" : "light";
    setTheme(next);
    setThemeState(next);
  }

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      title={theme === "light" ? "切换为暗色主题" : "切换为浅色主题"}
      aria-label={theme === "light" ? "切换为暗色主题" : "切换为浅色主题"}
    >
      <span className="theme-toggle-icon" aria-hidden>
        {theme === "light" ? "🌙" : "☀️"}
      </span>
      <span className="theme-toggle-label">
        {theme === "light" ? "暗色" : "浅色"}
      </span>
    </button>
  );
}
