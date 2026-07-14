import { describe, expect, it } from "vitest";
import { sliceByCodepoint, splitForHighlight } from "./unicodeHighlight";

describe("unicodeHighlight", () => {
  it("slices by unicode codepoint not utf16 code unit", () => {
    const text = "a😀b";
    expect(sliceByCodepoint(text, 1, 2)).toBe("😀");
    expect(sliceByCodepoint(text, 0, 3)).toBe("a😀b");
  });

  it("splitForHighlight returns before/highlight/after", () => {
    const parts = splitForHighlight("hello", 1, 4);
    expect(parts).toEqual({ before: "h", highlight: "ell", after: "o" });
  });
});
