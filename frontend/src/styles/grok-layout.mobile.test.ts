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
