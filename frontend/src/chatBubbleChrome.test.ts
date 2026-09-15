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
});

describe("fold chevron", () => {
  it("rotates a shared stroke chevron and respects reduced motion", () => {
    expect(css).toMatch(/\.fold-chevron\.is-open svg\s*\{[^}]*rotate\(90deg\)/);
    expect(css).toMatch(
      /@media \(prefers-reduced-motion: reduce\)\s*\{\s*\n\s*\.fold-chevron svg\s*\{[^}]*transition:\s*none;/,
    );
  });
});
