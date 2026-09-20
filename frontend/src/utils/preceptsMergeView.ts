import { diffLines } from "diff";
import { buildDocDiff, type DiffLine } from "./docDiff";

export type MergePick = "ours" | "theirs" | "both";

export type ConflictSides = {
  base: string;
  ours: string;
  theirs: string;
};

export type FoldedDiffRow =
  | { kind: "line"; line: DiffLine; index: number }
  | { kind: "fold"; count: number; start: number; end: number };

export function sideDiff(base: string, side: string): DiffLine[] {
  return buildDocDiff(base, side);
}

export function hunkTitle(hunk: ConflictSides): string {
  const heads = unique(
    [...headingNames(hunk.ours), ...headingNames(hunk.theirs)],
  );
  if (heads.length) return heads.join(" · ");
  const line =
    firstMeaningfulLine(hunk.ours) ||
    firstMeaningfulLine(hunk.theirs) ||
    firstMeaningfulLine(hunk.base);
  return line ? trimHeading(line) : "这段两边都改了";
}

export function combineHunk(ours: string, theirs: string): string {
  const a = ours ?? "";
  const b = theirs ?? "";
  if (!a.trim()) return b;
  if (!b.trim()) return a;
  if (a === b) return a;
  let out = "";
  for (const change of diffLines(a, b)) {
    out += change.value;
  }
  return out.endsWith("\n") || out.length === 0 ? out : `${out}\n`;
}

export function pickedHunkText(hunk: ConflictSides, pick: MergePick): string {
  if (pick === "ours") return hunk.ours;
  if (pick === "theirs") return hunk.theirs;
  return combineHunk(hunk.ours, hunk.theirs);
}

export function initialMergeDraft(pending: {
  ours?: string;
  theirs?: string;
  base?: string;
  proposed: string;
  conflicts: ConflictSides[];
}): string {
  const ours = pending.ours || pending.proposed || "";
  const fromProposed = applyAllBoth(pending.proposed || ours, pending.conflicts);
  const fromOurs = applyAllBoth(ours, pending.conflicts);
  const extra = exclusiveHeadings(
    pending.base || "",
    pending.ours || "",
    pending.theirs || "",
    pending.conflicts,
  );
  const score = (text: string) =>
    extra.ours.filter((name) => text.includes(name)).length +
    extra.theirs.filter((name) => text.includes(name)).length;
  if (score(fromProposed) >= score(fromOurs) && fromProposed.trim()) {
    return fromProposed;
  }
  return fromOurs;
}

function applyAllBoth(seed: string, conflicts: ConflictSides[]): string {
  let draft = seed;
  for (const hunk of conflicts) {
    draft = applyHunkPick(draft, hunk, hunk.ours, "both");
  }
  return draft;
}

export function applyHunkPick(
  draft: string,
  hunk: ConflictSides,
  previous: string,
  pick: MergePick,
): string {
  const next = pickedHunkText(hunk, pick);
  if (previous && draft.includes(previous)) {
    return replaceOnce(draft, previous, next);
  }
  if (hunk.ours && draft.includes(hunk.ours)) {
    return replaceOnce(draft, hunk.ours, next);
  }
  if (hunk.theirs && draft.includes(hunk.theirs)) {
    return replaceOnce(draft, hunk.theirs, next);
  }
  return draft;
}

export function changeCounts(lines: DiffLine[]): { plus: number; minus: number } {
  let plus = 0;
  let minus = 0;
  for (const line of lines) {
    if (line.type === "added") plus += 1;
    else if (line.type === "removed") minus += 1;
  }
  return { plus, minus };
}

export function exclusiveHeadings(
  base: string,
  ours: string,
  theirs: string,
  conflicts: ConflictSides[],
): { ours: string[]; theirs: string[] } {
  const conflictHeads = new Set(
    conflicts.flatMap((hunk) => [
      ...headingNames(hunk.ours),
      ...headingNames(hunk.theirs),
    ]),
  );
  const baseHeads = new Set(headingNames(base));
  const oursHeads = headingNames(ours);
  const theirsHeads = headingNames(theirs);
  const theirsSet = new Set(theirsHeads);
  const oursSet = new Set(oursHeads);
  return {
    ours: unique(
      oursHeads.filter(
        (name) =>
          !baseHeads.has(name) && !theirsSet.has(name) && !conflictHeads.has(name),
      ),
    ),
    theirs: unique(
      theirsHeads.filter(
        (name) =>
          !baseHeads.has(name) && !oursSet.has(name) && !conflictHeads.has(name),
      ),
    ),
  };
}

export function foldUnchanged(
  lines: DiffLine[],
  context = 2,
  minFold = 6,
): FoldedDiffRow[] {
  const out: FoldedDiffRow[] = [];
  let i = 0;
  while (i < lines.length) {
    if (lines[i]?.type !== "unchanged") {
      out.push({ kind: "line", line: lines[i]!, index: i });
      i += 1;
      continue;
    }
    let j = i;
    while (j < lines.length && lines[j]?.type === "unchanged") j += 1;
    const run = j - i;
    if (run < minFold + context * 2) {
      for (let k = i; k < j; k++) {
        out.push({ kind: "line", line: lines[k]!, index: k });
      }
    } else {
      for (let k = i; k < i + context; k++) {
        out.push({ kind: "line", line: lines[k]!, index: k });
      }
      out.push({
        kind: "fold",
        count: run - context * 2,
        start: i + context,
        end: j - context,
      });
      for (let k = j - context; k < j; k++) {
        out.push({ kind: "line", line: lines[k]!, index: k });
      }
    }
    i = j;
  }
  return out;
}

function headingNames(text: string): string[] {
  return (text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => /^#{1,3}\s+/.test(line))
    .map(trimHeading);
}

function firstMeaningfulLine(text: string): string {
  return (
    (text || "")
      .split("\n")
      .map((line) => line.trim())
      .find((line) => line.length > 0) || ""
  );
}

function trimHeading(line: string): string {
  return line.replace(/^#{1,6}\s+/, "").replace(/^[一二三四五六七八九十]+、/, "");
}

function unique(items: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    if (seen.has(item)) continue;
    seen.add(item);
    out.push(item);
  }
  return out;
}

export function lineRange(
  doc: string,
  snippet: string,
): { start: number; end: number } | null {
  const needle = snippet || "";
  if (!needle.trim()) return null;
  let at = doc.indexOf(needle);
  let len = needle.length;
  if (at < 0) {
    const trimmed = needle.trim();
    at = doc.indexOf(trimmed);
    len = trimmed.length;
    if (at < 0) return null;
  }
  const start = doc.slice(0, at).split("\n").length - 1;
  let last = at + len;
  if (last > 0 && doc[last - 1] === "\n") last -= 1;
  const end = doc.slice(0, last).split("\n").length;
  return { start, end: Math.max(start + 1, end) };
}

export function hunkIndexAtLine(
  ranges: Array<{ start: number; end: number } | null>,
  line: number,
): number {
  return ranges.findIndex(
    (range) => range != null && line >= range.start && line < range.end,
  );
}

export type HunkSpan = { start: number; end: number };

export function locateHunkSpans(
  draft: string,
  bodies: string[],
): Array<HunkSpan | null> {
  const out: Array<HunkSpan | null> = [];
  let from = 0;
  for (const body of bodies) {
    if (!body) {
      out.push(null);
      continue;
    }
    const at = draft.indexOf(body, from);
    if (at < 0) {
      out.push(null);
      continue;
    }
    out.push({ start: at, end: at + body.length });
    from = at + body.length;
  }
  return out;
}

export function firstEdit(
  prev: string,
  next: string,
): { at: number; oldLen: number; newLen: number } | null {
  if (prev === next) return null;
  let i = 0;
  const limit = Math.min(prev.length, next.length);
  while (i < limit && prev[i] === next[i]) i += 1;
  let a = prev.length;
  let b = next.length;
  while (a > i && b > i && prev[a - 1] === next[b - 1]) {
    a -= 1;
    b -= 1;
  }
  return { at: i, oldLen: a - i, newLen: b - i };
}

function mapPos(
  pos: number,
  at: number,
  oldLen: number,
  newLen: number,
  after: boolean,
): number {
  const oldEnd = at + oldLen;
  if (pos < at || (pos === at && !after)) return pos;
  if (pos > oldEnd || (pos === oldEnd && after)) return pos + (newLen - oldLen);
  return after ? at + newLen : at;
}

export function shiftSpans(
  spans: Array<HunkSpan | null>,
  at: number,
  oldLen: number,
  newLen: number,
): Array<HunkSpan | null> {
  return spans.map((span) => {
    if (!span) return span;
    const start = mapPos(span.start, at, oldLen, newLen, false);
    const end = mapPos(span.end, at, oldLen, newLen, true);
    return { start, end: Math.max(start, end) };
  });
}

export function replaceSpan(draft: string, span: HunkSpan, next: string): string {
  return draft.slice(0, span.start) + next + draft.slice(span.end);
}

function replaceOnce(haystack: string, needle: string, next: string): string {
  if (!needle) return haystack + (haystack.endsWith("\n") ? "" : "\n") + next;
  const at = haystack.indexOf(needle);
  if (at < 0) return haystack;
  return haystack.slice(0, at) + next + haystack.slice(at + needle.length);
}
