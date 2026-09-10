import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const css = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "grok-layout.css"),
  "utf8",
);

describe("mobile three-pane grid", () => {
  it("forces chat onto column 1 so an empty thread cannot shrink into a right-side implicit track", () => {
    expect(css).toMatch(
      /\.app-shell--mobile\.app-shell--three-pane \.main-panel,\s*\n\s*\.app-shell--mobile\.app-shell--three-pane \.role-config-panel\s*\{\s*\n\s*grid-column:\s*1;/,
    );
  });
});
