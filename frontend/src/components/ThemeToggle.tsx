import { useEffect, useState } from "react";
import { getStoredTheme, setTheme, type Theme } from "../theme";

type Props = {
  /** 侧栏底栏：图标 +「主题」，避免和「聊天通道 / 设置」抢字。 */
  compact?: boolean;
};

export function ThemeToggle({ compact = false }: Props) {
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

  const action = theme === "light" ? "切换为暗色主题" : "切换为浅色主题";

  return (
    <button
      type="button"
      className={`theme-toggle${compact ? " theme-toggle--dock" : ""}`}
      onClick={toggle}
      title={compact ? `主题 · ${action}` : action}
      aria-label={compact ? `主题，${action}` : action}
    >
      <span className="theme-toggle-icon" aria-hidden>
        {theme === "light" ? "🌙" : "☀️"}
      </span>
      <span className="theme-toggle-label">
        {compact ? "主题" : theme === "light" ? "暗色" : "浅色"}
      </span>
    </button>
  );
}
