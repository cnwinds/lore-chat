import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const indexCss = readFileSync(join(here, "../index.css"), "utf8");
const loreCss = readFileSync(join(here, "lore-theme.css"), "utf8");

describe("kb special group chrome", () => {
  it("paints one rounded shell and keeps middle rows square", () => {
    expect(indexCss).toMatch(
      /\.file-tree-special-group\s*\{[^}]*background:\s*var\(--kb-special-bg\)/,
    );
    expect(indexCss).toMatch(
      /\.file-tree-row\.kb-special\s*\{[^}]*background:\s*transparent/,
    );
    expect(loreCss).toMatch(
      /\.file-tree-special-group\s*\{[^}]*border-radius:\s*var\(--radius-md\)/,
    );
    expect(loreCss).toMatch(
      /\.file-tree-special-group\s*\{[^}]*overflow:\s*hidden/,
    );
    expect(loreCss).toMatch(
      /\.file-tree-special-group \.file-tree-row,\s*\n\s*\.file-tree-special-group \.file-tree-row:hover,\s*\n\s*\.file-tree-special-group \.file-tree-row\.selected\s*\{\s*\n\s*border-radius:\s*0;/,
    );
  });
});
