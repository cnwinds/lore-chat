export const UNICODE_CODEPOINT_V1 = "unicode-codepoint-v1";

export function isHighlightOffsetVersion(offsetVersion?: string): boolean {
  return !offsetVersion || offsetVersion === UNICODE_CODEPOINT_V1;
}

export function sliceByCodepoint(text: string, start: number, end: number): string {
  const chars = Array.from(text);
  return chars.slice(start, end).join("");
}

export function splitForHighlight(
  text: string,
  start: number,
  end: number,
): { before: string; highlight: string; after: string } {
  const chars = Array.from(text);
  return {
    before: chars.slice(0, start).join(""),
    highlight: chars.slice(start, end).join(""),
    after: chars.slice(end).join(""),
  };
}

export type TimelineTextSpan = {
  timelineIndex: number;
  content: string;
  globalStart: number;
  globalEnd: number;
};

/** Collect top-level timeline text blocks with global codepoint spans (matches message.text). */
export function collectTimelineTextSpans(
  timeline: Array<{ type?: string; content?: string }>,
): TimelineTextSpan[] {
  const spans: TimelineTextSpan[] = [];
  let global = 0;
  timeline.forEach((block, timelineIndex) => {
    if (block.type !== "text" || !block.content) return;
    const len = Array.from(block.content).length;
    spans.push({
      timelineIndex,
      content: block.content,
      globalStart: global,
      globalEnd: global + len,
    });
    global += len;
  });
  return spans;
}

export type BlockHighlightRange = { start: number; end: number };

/** Map a global [start,end) onto per-timeline-index local highlight ranges. */
export function mapGlobalRangeToTimelineHighlights(
  timeline: Array<{ type?: string; content?: string }>,
  start: number,
  end: number,
): Map<number, BlockHighlightRange> {
  const out = new Map<number, BlockHighlightRange>();
  if (start >= end) return out;
  for (const span of collectTimelineTextSpans(timeline)) {
    const overlapStart = Math.max(start, span.globalStart);
    const overlapEnd = Math.min(end, span.globalEnd);
    if (overlapStart < overlapEnd) {
      out.set(span.timelineIndex, {
        start: overlapStart - span.globalStart,
        end: overlapEnd - span.globalStart,
      });
    }
  }
  return out;
}