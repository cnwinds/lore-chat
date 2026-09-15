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

  it("keeps the assistant colophon in one left-aligned cluster", () => {
    expect(css).toMatch(
      /\.chat-meta-assistant\s*\{[^}]*justify-content:\s*flex-start;/,
    );
    expect(css).not.toMatch(/\.chat-meta-actions\s*\{[^}]*margin-left:\s*auto/);
    expect(css).not.toMatch(/\.chat-meta-info\s*\{/);
  });
});

describe("overlay scrollbars", () => {
  it("hides native scrollbars so they do not occupy layout", () => {
    expect(css).toMatch(/\*\s*\{[^}]*scrollbar-width:\s*none;/);
    expect(css).toMatch(/\*::-webkit-scrollbar\s*\{[^}]*display:\s*none;/);
    expect(css).not.toMatch(/\*\s*\{[^}]*scrollbar-width:\s*thin;/);
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
