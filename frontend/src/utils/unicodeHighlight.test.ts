import { describe, expect, it } from "vitest";
import {
  collectTimelineTextSpans,
  isHighlightOffsetVersion,
  mapGlobalRangeToTimelineHighlights,
  sliceByCodepoint,
  splitForHighlight,
} from "./unicodeHighlight";

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

  it("isHighlightOffsetVersion accepts default and unicode-codepoint-v1", () => {
    expect(isHighlightOffsetVersion()).toBe(true);
    expect(isHighlightOffsetVersion("unicode-codepoint-v1")).toBe(true);
    expect(isHighlightOffsetVersion("utf16-v1")).toBe(false);
  });

  it("collectTimelineTextSpans tracks global offsets across blocks", () => {
    const timeline = [
      { type: "text", content: "Hello" },
      { type: "tool", id: "t1" },
      { type: "text", content: "World" },
    ];
    const spans = collectTimelineTextSpans(timeline);
    expect(spans).toHaveLength(2);
    expect(spans[0]).toMatchObject({ timelineIndex: 0, globalStart: 0, globalEnd: 5 });
    expect(spans[1]).toMatchObject({ timelineIndex: 2, globalStart: 5, globalEnd: 10 });
  });

  it("mapGlobalRangeToTimelineHighlights maps onto correct text block", () => {
    const timeline = [
      { type: "text", content: "Hello" },
      { type: "tool", id: "t1" },
      { type: "text", content: "World" },
    ];
    const mapped = mapGlobalRangeToTimelineHighlights(timeline, 6, 10);
    expect(mapped.get(2)).toEqual({ start: 1, end: 5 });
    expect(mapped.has(0)).toBe(false);
  });

  it("mapGlobalRangeToTimelineHighlights spans multiple blocks", () => {
    const timeline = [
      { type: "text", content: "ab" },
      { type: "text", content: "cd" },
    ];
    const mapped = mapGlobalRangeToTimelineHighlights(timeline, 1, 3);
    expect(mapped.get(0)).toEqual({ start: 1, end: 2 });
    expect(mapped.get(1)).toEqual({ start: 0, end: 1 });
  });
});
