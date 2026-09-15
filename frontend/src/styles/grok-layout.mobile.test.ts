import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const css = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "grok-layout.css"),
  "utf8",
);

describe("three-pane grid", () => {
  it("reserves a zero-width doc track that expands when a pinned panel is present", () => {
    expect(css).toMatch(/--app-doc-col:\s*0px;/);
    expect(css).toMatch(
      /\.app-shell--three-pane:has\(>\s*\.doc-panel\),\s*\n\s*\.app-shell--three-pane\.app-shell--doc-pinned\s*\{\s*\n\s*--app-doc-col:\s*auto;/,
    );
    expect(css).toMatch(
      /\.app-shell--three-pane \.doc-panel\s*\{\s*\n\s*grid-column:\s*3;/,
    );
    expect(css).toMatch(
      /\.role-config-panel\s*\{\s*\n\s*grid-column:\s*4;/,
    );
  });

  it("keeps chat in column 2; channel UI is a float overlay, not a grid track", () => {
    expect(css).not.toMatch(/--app-channel-col/);
    expect(css).toMatch(
      /\.app-shell--three-pane \.main-panel\s*\{\s*\n\s*grid-column:\s*2;/,
    );
  });

  it("does not collapse the whole grid to two columns when the role config is hidden", () => {
    expect(css).toMatch(
      /\.app-shell--three-pane\.app-shell--config-collapsed\s*\{\s*\n\s*--app-config-col:\s*0px;/,
    );
    expect(css).not.toMatch(
      /\.app-shell--three-pane\.app-shell--config-collapsed\s*\{\s*\n\s*grid-template-columns:\s*var\(--app-left-width,\s*\d+px\)\s+1fr;/,
    );
  });
});

describe("mobile three-pane grid", () => {
  it("forces chat onto column 1 so an empty thread cannot shrink into a right-side implicit track", () => {
    expect(css).toMatch(
      /\.app-shell--mobile\.app-shell--three-pane \.main-panel,\s*\n\s*\.app-shell--mobile\.app-shell--three-pane \.role-config-panel,\s*\n\s*\.app-shell--mobile\.app-shell--three-pane \.doc-panel\s*\{\s*\n\s*grid-column:\s*1;/,
    );
  });

  it("opens role or group settings as a right-side sheet instead of hiding them", () => {
    expect(css).toMatch(
      /\.app-shell--mobile \.role-config-panel\s*\{\s*\n\s*position:\s*fixed;/,
    );
    expect(css).not.toMatch(
      /\.app-shell--mobile \.role-config-panel\s*\{\s*\n\s*display:\s*none;/,
    );
  });
});

describe("kb sidebar chrome", () => {
  it("insets the knowledge tree and leaves a quiet canvas before chat", () => {
    expect(css).toMatch(/\.kb-sidebar-head\s*\{[^}]*padding:\s*8px 12px 6px;/);
    expect(css).toMatch(/\.kb-sidebar-scroll\s*\{[^}]*padding:\s*4px 12px 12px;/);
    expect(css).toMatch(/--app-chat-inset:\s*12px;/);
    expect(css).toMatch(
      /\.app-shell--three-pane \.main-panel\s*\{[^}]*margin-left:\s*var\(--app-chat-inset\);/,
    );
  });

  it("keeps the left dock footer on its own grid row", () => {
    expect(css).toMatch(
      /\.app-shell--three-pane \.app-shell-left\s*\{[^}]*grid-template-rows:\s*minmax\(0,\s*1fr\)\s+auto;/,
    );
    expect(css).toMatch(
      /\.app-shell-left \.sidebar-footer\s*\{[^}]*grid-row:\s*2;/,
    );
  });

  it("keeps splitters as the same invisible hit target", () => {
    expect(css).toMatch(/--app-split-hit:\s*6px;/);
    expect(css).toMatch(
      /\.app-shell-left-resizer\s*\{[^}]*width:\s*var\(--app-split-hit\);/,
    );
    expect(css).toMatch(
      /\.app-shell-left-v-resizer::after\s*\{[^}]*height:\s*var\(--app-split-hit\);/,
    );
    expect(css).toMatch(/\.app-shell-left-v-resizer\s*\{[^}]*flex:\s*0 0 0;/);
    expect(css).not.toMatch(/--app-split-gap:/);
  });
});

describe("group avatar collage", () => {
  it("uses a fixed 2x2 grid so missing members leave empty cells", () => {
    expect(css).toMatch(
      /\.group-avatar\s*\{[^}]*grid-template-columns:\s*1fr 1fr;[^}]*grid-template-rows:\s*1fr 1fr;/,
    );
    expect(css).not.toMatch(/\.group-avatar--3\s*>\s*:first-child/);
    expect(css).toMatch(
      /\.group-avatar\s+\.role-avatar\s+img\s*\{[^}]*object-fit:\s*contain;/,
    );
  });
});

describe("group avatar mark", () => {
  it("keeps the group type chip at top-left and the busy dot at bottom-right", () => {
    expect(css).toMatch(
      /\.group-avatar-mark\s*\{[^}]*\bleft:\s*-3px;[^}]*\btop:\s*-3px;/,
    );
    expect(css).not.toMatch(
      /\.group-avatar-mark\s*\{[^}]*\b(?:right|bottom):/,
    );
    expect(css).toMatch(
      /\.role-item-busy\s*\{[^}]*\bright:\s*-1px;[^}]*\bbottom:\s*-1px;/,
    );
    expect(css).toMatch(/\.group-avatar-host\s*\{[^}]*border-radius:\s*30%;/);
  });
});
