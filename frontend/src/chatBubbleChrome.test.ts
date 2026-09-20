import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const css = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "index.css"),
  "utf8",
);

describe("chat bubble chrome", () => {
  it("does not draw a hairline above timestamps or the sources row", () => {
    expect(css).not.toMatch(/\.chat-meta\s*\{[^}]*border-top:/);
    expect(css).not.toMatch(/\.chat-sources\s*\{[^}]*border-top:/);
  });

  it("tucks the user copy button next to the timestamp with a gap", () => {
    expect(css).toMatch(/\.chat-meta-user\s*\{[^}]*justify-content:\s*flex-end;/);
    expect(css).not.toMatch(/\.chat-meta-spacer/);
  });

  it("shrinks the mobile sheet FAB to an icon so it does not cover bubbles", () => {
    expect(css).toMatch(/\.share-sheet-fab--compact\s*\{[^}]*width:\s*40px;/);
    expect(css).toMatch(
      /\.share-sheet-fab--compact \.share-sheet-fab-badge\s*\{[^}]*position:\s*absolute;/,
    );
  });

  it("does not reserve a side column for group role avatars", () => {
    expect(css).toMatch(
      /\.chat-row-group-col\s*\{[^}]*max-width:\s*min\(680px,\s*100%\);/,
    );
    expect(css).toMatch(/\.chat-row-group-head\s*\{/);
    expect(css).toMatch(
      /\.chat-panel--mobile \.chat-row-group-col\s*\{[^}]*max-width:\s*100%;/,
    );
    expect(css).not.toMatch(/calc\(100% - 40px\)/);
  });

  it("keeps the assistant colophon in one left-aligned cluster", () => {
    expect(css).toMatch(
      /\.chat-meta-assistant\s*\{[^}]*justify-content:\s*flex-start;/,
    );
    expect(css).not.toMatch(/\.chat-meta-actions\s*\{[^}]*margin-left:\s*auto/);
    expect(css).not.toMatch(/\.chat-meta-info\s*\{/);
  });

  it("hides assistant token usage on the mobile breakpoint", () => {
    expect(css).toMatch(
      /@media \(max-width: 768px\)\s*\{\s*\n\s*\.chat-meta-tokens\s*\{[^}]*display:\s*none;/,
    );
  });

  it("reveals exact token counts on hover in a compact slip", () => {
    expect(css).toMatch(
      /\.chat-meta-tokens:hover \.chat-meta-tokens-tip,\s*\n\s*\.chat-meta-tokens:focus-visible \.chat-meta-tokens-tip\s*\{[^}]*visibility:\s*visible;/,
    );
  });
});

describe("fixed overflow menu", () => {
  it("stacks above the mobile nav drawer and settings sheet", () => {
    expect(css).toMatch(/\.doc-overflow-menu--fixed\s*\{[^}]*z-index:\s*1300;/);
  });
});

describe("left dock chrome", () => {
  it("keeps 主题 / 聊天通道 / 设置 compact but still tappable", () => {
    expect(css).toMatch(/\.theme-toggle\s*\{[^}]*min-height:\s*36px;/);
    expect(css).toMatch(/\.sidebar-dock-btn\s*\{[^}]*min-height:\s*36px;/);
    expect(css).toMatch(/\.sidebar-settings-btn\s*\{[^}]*min-height:\s*36px;/);
  });
});

describe("overlay scrollbars", () => {
  it("hides native scrollbars so they do not occupy layout", () => {
    expect(css).toMatch(/\*\s*\{[^}]*scrollbar-width:\s*none;/);
    expect(css).toMatch(/\*::-webkit-scrollbar\s*\{[^}]*display:\s*none;/);
    expect(css).not.toMatch(/\*\s*\{[^}]*scrollbar-width:\s*thin;/);
  });

  it("paints an overlay rail only while visible", () => {
    expect(css).toMatch(/\.lore-scroll-rail\s*\{[^}]*pointer-events:\s*none;/);
    expect(css).toMatch(/\.lore-scroll-rail\s*\{[^}]*visibility:\s*hidden;/);
    expect(css).toMatch(
      /\.lore-scroll-rail\.is-visible\s*\{[^}]*pointer-events:\s*auto;/,
    );
    expect(css).toMatch(
      /\.lore-scroll-thumb\s*\{[^}]*color-mix\(in srgb,\s*var\(--text\)/,
    );
  });
});

describe("fold chevron", () => {
  it("rotates a shared stroke chevron and respects reduced motion", () => {
    expect(css).toMatch(/\.fold-chevron\.is-open svg\s*\{[^}]*rotate\(90deg\)/);
    expect(css).toMatch(
      /@media \(prefers-reduced-motion: reduce\)\s*\{\s*\n\s*\.fold-chevron svg\s*\{[^}]*transition:\s*none;/,
    );
  });
});
