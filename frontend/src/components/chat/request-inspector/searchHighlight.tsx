import type { ReactNode } from "react";

export function countMatches(text: string, query: string): number {
  const q = query.trim();
  if (!q || !text) return 0;
  const lower = text.toLowerCase();
  const needle = q.toLowerCase();
  let n = 0;
  let pos = 0;
  while (true) {
    const i = lower.indexOf(needle, pos);
    if (i < 0) break;
    n += 1;
    pos = i + needle.length;
  }
  return n;
}

export function highlightMatches(
  text: string,
  query: string,
  activeGlobalIndex: number,
  globalOffset: number,
): { nodes: ReactNode; matchCount: number } {
  const q = query.trim();
  if (!q || !text) return { nodes: text, matchCount: 0 };
  const lower = text.toLowerCase();
  const needle = q.toLowerCase();
  const parts: ReactNode[] = [];
  let pos = 0;
  let localIdx = 0;
  while (true) {
    const i = lower.indexOf(needle, pos);
    if (i < 0) break;
    if (i > pos) parts.push(text.slice(pos, i));
    const gIdx = globalOffset + localIdx;
    parts.push(
      <mark
        key={`${globalOffset}-${localIdx}`}
        className={
          gIdx === activeGlobalIndex
            ? "reqinspector-mark reqinspector-mark--active"
            : "reqinspector-mark"
        }
      >
        {text.slice(i, i + needle.length)}
      </mark>,
    );
    pos = i + needle.length;
    localIdx += 1;
  }
  if (pos < text.length) parts.push(text.slice(pos));
  return { nodes: parts, matchCount: localIdx };
}
