import { describe, expect, it } from "vitest";
import {
  isDocMarkdownDirty,
  isMarkdownCosmeticallyEqual,
  normalizeMarkdownForCompare,
} from "./docMarkdown";

describe("normalizeMarkdownForCompare", () => {
  it("treats escaped ordered-list markers as equivalent", () => {
    const file = "5\\. 客户想上线一个 AI 产品";
    const editor = "5. 客户想上线一个 AI 产品";
    expect(isMarkdownCosmeticallyEqual(file, editor)).toBe(true);
  });

  it("treats * and - bullets as equivalent", () => {
    const file = "- 第一项\n- 第二项";
    const editor = "* 第一项\n* 第二项";
    expect(isMarkdownCosmeticallyEqual(file, editor)).toBe(true);
  });

  it("ignores extra blank lines between list items", () => {
    const file = "- a\n- b\n- c";
    const editor = "- a\n\n- b\n\n\n- c";
    expect(isMarkdownCosmeticallyEqual(file, editor)).toBe(true);
  });
});

describe("isDocMarkdownDirty", () => {
  it("ignores trailing whitespace", () => {
    expect(isDocMarkdownDirty("a\n", "a")).toBe(false);
  });

  it("detects real content changes", () => {
    expect(isDocMarkdownDirty("- a", "- b")).toBe(true);
  });
});

describe("normalizeMarkdownForCompare regression", () => {
  it("preserves distinct paragraphs", () => {
    const a = "段落一\n\n段落二";
    const b = "段落一\n段落二";
    expect(normalizeMarkdownForCompare(a)).not.toBe(
      normalizeMarkdownForCompare(b),
    );
  });
});
