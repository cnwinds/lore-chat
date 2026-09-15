import { useEffect, useRef, useState } from "react";
import {
  THEME_CATALOG,
  THEME_IDS,
  getStoredTheme,
  setTheme,
  subscribeThemeChange,
  type Theme,
} from "../theme";
import { FixedOverflowMenu } from "./FixedOverflowMenu";

type Props = {
  /** 侧栏底栏：图标 +「主题」，避免和「聊天通道 / 设置」抢字。 */
  compact?: boolean;
};

function ThemeSwatch({
  swatches,
  className,
}: {
  swatches: readonly [string, string];
  className: string;
}) {
  return (
    <span className={className} aria-hidden>
      <span style={{ background: swatches[0] }} />
      <span style={{ background: swatches[1] }} />
    </span>
  );
}

export function ThemeToggle({ compact = false }: Props) {
  const [theme, setThemeState] = useState<Theme>(() => getStoredTheme());
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const meta = THEME_CATALOG[theme];

  useEffect(() => subscribeThemeChange(setThemeState), []);

  const title = compact ? `主题 · ${meta.label}` : `当前主题：${meta.label}`;
  const ariaLabel = compact
    ? `主题，当前为${meta.label}`
    : `选择主题，当前为${meta.label}`;

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className={`theme-toggle${compact ? " theme-toggle--dock" : ""}`}
        onClick={() => setOpen((v) => !v)}
        title={title}
        aria-label={ariaLabel}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <ThemeSwatch swatches={meta.swatches} className="theme-toggle-swatch" />
        <span className="theme-toggle-label">{compact ? "主题" : meta.label}</span>
      </button>
      <FixedOverflowMenu
        open={open}
        anchorRef={btnRef}
        align="start"
        label="选择主题"
        className="theme-menu"
        onDismiss={() => setOpen(false)}
      >
        {THEME_IDS.map((id) => {
          const item = THEME_CATALOG[id];
          const selected = id === theme;
          return (
            <button
              key={id}
              type="button"
              role="menuitemradio"
              aria-checked={selected}
              className={`doc-overflow-item theme-menu-item${selected ? " is-active" : ""}`}
              onClick={() => {
                setTheme(id);
                setThemeState(id);
                setOpen(false);
              }}
            >
              <ThemeSwatch swatches={item.swatches} className="theme-menu-swatch" />
              <span>{item.label}</span>
              {selected ? (
                <span className="theme-menu-check" aria-hidden>
                  ✓
                </span>
              ) : null}
            </button>
          );
        })}
      </FixedOverflowMenu>
    </>
  );
}
