import { describe, expect, it } from "vitest";
import {
  isKbRelativeImagePath,
  isLikelyImagePath,
  restoreMarkdownImageSrcsForStorage,
  rewriteMarkdownImageSrcsForDisplay,
} from "./kbImageUrls";

describe("kbImageUrls", () => {
  it("detects relative kb image paths", () => {
    expect(isKbRelativeImagePath("generated/2026/a.png")).toBe(true);
    expect(isKbRelativeImagePath("https://cdn.example/a.png")).toBe(false);
    expect(isKbRelativeImagePath("/api/download?path=a.png")).toBe(false);
  });

  it("rewrites relative markdown images for display and restores for storage", () => {
    const src = "见图：![猫](generated/2026/cat.png) 完";
    const display = rewriteMarkdownImageSrcsForDisplay(src);
    expect(display).toContain("/api/download?");
    expect(display).toContain("path=");
    expect(restoreMarkdownImageSrcsForStorage(display)).toBe(src);
  });

  it("rejects unrestorable /api/download image srcs", () => {
    expect(() =>
      restoreMarkdownImageSrcsForStorage("![x](/api/download)"),
    ).toThrow(/相对路径/);
    expect(() =>
      restoreMarkdownImageSrcsForStorage(
        "![x](/api/attachments/signed/abc)",
      ),
    ).toThrow(/相对路径/);
  });

  it("leaves remote images alone", () => {
    const src = "![x](https://example.com/a.png)";
    expect(rewriteMarkdownImageSrcsForDisplay(src)).toBe(src);
  });

  it("isLikelyImagePath", () => {
    expect(isLikelyImagePath("a/b.PNG")).toBe(true);
    expect(isLikelyImagePath("notes/a.md")).toBe(false);
  });
});
