import { diffArrays, diffChars } from "diff";

/**
 * 三路合并的块模型：把 base / ours(现行) / theirs(官方) 三篇按行对齐成
 * 一串块（相同 / 单侧改动 / 冲突 / 手改），结果稿由块按状态拼出。
 * 簇划分与 backend/app/engine/text_merge3.py 同源：两侧对 base 的改动
 * 区间重叠则并为一个冲突簇，否则单侧改动直接并入结果。
 */

export type MergePick = "ours" | "theirs" | "both";

export type ConflictResolution = "pending" | MergePick | "custom" | "ignored";

export type WordSeg = { text: string; changed: boolean };

export type BaseBlock = {
  id: number;
  /** 块在结果稿里当前的行。 */
  lines: string[];
  /** 左右两栏里的行区间 [start, end)，用于高亮与连接线。 */
  oursRange: { start: number; end: number };
  theirsRange: { start: number; end: number };
};

export type EqualBlock = BaseBlock & { kind: "equal" };

export type SideBlock = BaseBlock & {
  kind: "side";
  side: "ours" | "theirs";
  state: "applied" | "ignored";
  baseLines: string[];
  wordSegs: WordSeg[][] | null;
};

export type ConflictBlock = BaseBlock & {
  kind: "conflict";
  baseLines: string[];
  oursLines: string[];
  theirsLines: string[];
  resolution: ConflictResolution;
  /** 展示行与另一侧的逐行词级差异；手改后为 null。 */
  wordSegs: WordSeg[][] | null;
  /** theirs 侧行 segmentation（给右栏词级高亮用）。 */
  wordSegsTheirs: WordSeg[][] | null;
};

export type CustomBlock = BaseBlock & { kind: "custom" };

export type MergeBlock = EqualBlock | SideBlock | ConflictBlock | CustomBlock;

export type LineRange = { start: number; end: number };

/** 行数统计与正文一致：空文本 0 行，多行按 \n 切。 */
export function toLines(text: string): string[] {
  if (text === "") return [];
  let t = text;
  if (t.endsWith("\n")) t = t.slice(0, -1);
  return t.split("\n");
}

export function linesText(lines: string[]): string {
  return lines.join("\n");
}

export function blockResultLines(block: MergeBlock): string[] {
  if (block.kind === "side") {
    return block.state === "applied" ? block.lines : block.baseLines;
  }
  return block.lines;
}

export function resultLines(blocks: MergeBlock[]): string[] {
  const out: string[] = [];
  for (const block of blocks) out.push(...blockResultLines(block));
  return out;
}

export function resultText(blocks: MergeBlock[]): string {
  return linesText(resultLines(blocks));
}

type Opcode = {
  tag: "equal" | "replace" | "insert" | "delete";
  baseStart: number;
  baseEnd: number;
  sideStart: number;
  sideEnd: number;
};

function opcodes(base: string[], side: string[]): Opcode[] {
  const out: Opcode[] = [];
  let bi = 0;
  let si = 0;
  for (const part of diffArrays(base, side)) {
    const count = part.count ?? part.value.length;
    if (part.added) {
      out.push({
        tag: "insert",
        baseStart: bi,
        baseEnd: bi,
        sideStart: si,
        sideEnd: si + count,
      });
      si += count;
    } else if (part.removed) {
      out.push({
        tag: "delete",
        baseStart: bi,
        baseEnd: bi + count,
        sideStart: si,
        sideEnd: si,
      });
      bi += count;
    } else {
      out.push({
        tag: "equal",
        baseStart: bi,
        baseEnd: bi + count,
        sideStart: si,
        sideEnd: si + count,
      });
      bi += count;
      si += count;
    }
  }
  return out;
}

/** 把相邻的删/增合成 replace 区间，便于两侧改动做区间重叠判定。 */
function editRanges(base: string[], side: string[]): Opcode[] {
  const raw = opcodes(base, side);
  const out: Opcode[] = [];
  for (const op of raw) {
    if (op.tag === "equal") continue;
    const prev = out[out.length - 1];
    if (prev && prev.baseEnd === op.baseStart && prev.sideEnd === op.sideStart) {
      prev.baseEnd = Math.max(prev.baseEnd, op.baseEnd);
      prev.sideEnd = Math.max(prev.sideEnd, op.sideEnd);
      prev.tag =
        prev.baseEnd > prev.baseStart && prev.sideEnd > prev.sideStart
          ? "replace"
          : prev.baseEnd > prev.baseStart
            ? "delete"
            : "insert";
      continue;
    }
    out.push({ ...op });
  }
  return out;
}

function overlaps(a: LineRange, b: LineRange): boolean {
  if (a.start === a.end && b.start === b.end) return a.start === b.start;
  if (a.start === a.end) return b.start <= a.start && a.start <= b.end;
  if (b.start === b.end) return a.start <= b.start && b.start <= a.end;
  return a.start < b.end && b.start < a.end;
}

/** base 上与 [blo,bhi) 对应的 side 行，起点处的插入计入，终点处不计。 */
function sideSpan(
  base: string[],
  side: string[],
  blo: number,
  bhi: number,
): string[] {
  const lines: string[] = [];
  const zero = blo === bhi;
  for (const op of editRanges(base, side)) {
    if (op.tag === "equal") {
      const lo = Math.max(op.baseStart, blo);
      const hi = Math.min(op.baseEnd, bhi);
      if (lo < hi) {
        const off = op.sideStart + (lo - op.baseStart);
        lines.push(...side.slice(off, off + (hi - lo)));
      }
      continue;
    }
    if (op.tag === "delete") continue;
    if (op.tag === "insert") {
      if (op.baseStart < blo || op.baseStart > bhi) continue;
      if (op.baseStart === bhi && !zero) continue;
      lines.push(...side.slice(op.sideStart, op.sideEnd));
      continue;
    }
    const lo = Math.max(op.baseStart, blo);
    const hi = Math.min(op.baseEnd, bhi);
    if (lo < hi) lines.push(...side.slice(op.sideStart, op.sideEnd));
  }
  return lines;
}

/** 与 text_merge3._clusters 一致：重叠的单侧改动并成簇。 */
function clusters(
  oursEdits: Opcode[],
  theirsEdits: Opcode[],
): Array<{ blo: number; bhi: number; oursChanged: boolean; theirsChanged: boolean }> {
  const items: Array<{ side: "a" | "t"; lo: number; hi: number }> = [];
  for (const e of oursEdits) items.push({ side: "a", lo: e.baseStart, hi: e.baseEnd });
  for (const e of theirsEdits) items.push({ side: "t", lo: e.baseStart, hi: e.baseEnd });
  items.sort((x, y) => x.lo - y.lo || x.hi - y.hi || (x.side === "a" ? -1 : 1));
  const out: Array<{
    blo: number;
    bhi: number;
    oursChanged: boolean;
    theirsChanged: boolean;
  }> = [];
  if (!items.length) return out;
  let { lo, hi } = items[0];
  let sawOurs = items[0].side === "a";
  let sawTheirs = items[0].side === "t";
  for (const item of items.slice(1)) {
    if (overlaps({ start: lo, end: hi }, { start: item.lo, end: item.hi })) {
      lo = Math.min(lo, item.lo);
      hi = Math.max(hi, item.hi);
      sawOurs = sawOurs || item.side === "a";
      sawTheirs = sawTheirs || item.side === "t";
      continue;
    }
    out.push({ blo: lo, bhi: hi, oursChanged: sawOurs, theirsChanged: sawTheirs });
    lo = item.lo;
    hi = item.hi;
    sawOurs = item.side === "a";
    sawTheirs = item.side === "t";
  }
  out.push({ blo: lo, bhi: hi, oursChanged: sawOurs, theirsChanged: sawTheirs });
  return out;
}

function wordSegsOf(base: string[], side: string[]): WordSeg[][] | null {
  if (base.length !== side.length) return null;
  const out: WordSeg[][] = [];
  for (let i = 0; i < base.length; i++) {
    const b = base[i];
    const s = side[i];
    if (b === s) {
      out.push([{ text: s, changed: false }]);
      continue;
    }
    if (b.length > 400 || s.length > 400) {
      out.push([{ text: s, changed: true }]);
      continue;
    }
    const segs: WordSeg[] = [];
    for (const part of diffChars(b, s)) {
      // 只保留展示行（side）中存在的文字：base 独有的片段不能拼进展示行
      if (part.removed) continue;
      if (!part.value) continue;
      const changed = Boolean(part.added);
      const prev = segs[segs.length - 1];
      if (prev && prev.changed === changed) prev.text += part.value;
      else segs.push({ text: part.value, changed });
    }
    out.push(segs);
  }
  return out;
}

function emptyRange(at: number): LineRange {
  return { start: at, end: at };
}

export function buildMergeBlocks(
  baseText: string,
  oursText: string,
  theirsText: string,
): MergeBlock[] {
  const base = toLines(baseText);
  const ours = toLines(oursText);
  const theirs = toLines(theirsText);
  if (linesText(ours) === linesText(theirs)) {
    return [
      {
        id: 0,
        kind: "equal",
        lines: ours,
        oursRange: { start: 0, end: ours.length },
        theirsRange: { start: 0, end: theirs.length },
      },
    ];
  }

  const oursEdits = editRanges(base, ours);
  const theirsEdits = editRanges(base, theirs);
  const groups = clusters(oursEdits, theirsEdits);

  const out: MergeBlock[] = [];
  let id = 0;
  let baseAt = 0;
  let oursAt = 0;
  let theirsAt = 0;

  const pushEqual = (lines: string[]) => {
    if (!lines.length) return;
    out.push({
      id: id++,
      kind: "equal",
      lines,
      oursRange: { start: oursAt, end: oursAt + lines.length },
      theirsRange: { start: theirsAt, end: theirsAt + lines.length },
    });
    oursAt += lines.length;
    theirsAt += lines.length;
    baseAt += lines.length;
  };

  for (const group of groups) {
    pushEqual(base.slice(baseAt, group.blo));
    const baseLines = base.slice(group.blo, group.bhi);
    const oursLines = sideSpan(base, ours, group.blo, group.bhi);
    const theirsLines = sideSpan(base, theirs, group.blo, group.bhi);
    if (group.oursChanged && !group.theirsChanged) {
      out.push({
        id: id++,
        kind: "side",
        side: "ours",
        state: "applied",
        lines: oursLines,
        baseLines,
        wordSegs: wordSegsOf(baseLines, oursLines),
        oursRange: { start: oursAt, end: oursAt + oursLines.length },
        theirsRange: { start: theirsAt, end: theirsAt + baseLines.length },
      });
      oursAt += oursLines.length;
      theirsAt += baseLines.length;
      baseAt = group.bhi;
      continue;
    }
    if (group.theirsChanged && !group.oursChanged) {
      out.push({
        id: id++,
        kind: "side",
        side: "theirs",
        state: "applied",
        lines: theirsLines,
        baseLines,
        wordSegs: wordSegsOf(baseLines, theirsLines),
        oursRange: { start: oursAt, end: oursAt + baseLines.length },
        theirsRange: { start: theirsAt, end: theirsAt + theirsLines.length },
      });
      oursAt += baseLines.length;
      theirsAt += theirsLines.length;
      baseAt = group.bhi;
      continue;
    }
    if (linesText(oursLines) === linesText(theirsLines)) {
      out.push({
        id: id++,
        kind: "equal",
        lines: oursLines,
        oursRange: { start: oursAt, end: oursAt + oursLines.length },
        theirsRange: { start: theirsAt, end: theirsAt + theirsLines.length },
      });
      oursAt += oursLines.length;
      theirsAt += theirsLines.length;
      baseAt = group.bhi;
      continue;
    }
    out.push({
      id: id++,
      kind: "conflict",
      baseLines,
      oursLines,
      theirsLines,
      resolution: "pending",
      lines: oursLines,
      wordSegs: wordSegsOf(theirsLines, oursLines),
      wordSegsTheirs: wordSegsOf(oursLines, theirsLines),
      oursRange: { start: oursAt, end: oursAt + oursLines.length },
      theirsRange: { start: theirsAt, end: theirsAt + theirsLines.length },
    });
    oursAt += oursLines.length;
    theirsAt += theirsLines.length;
    baseAt = group.bhi;
  }
  pushEqual(base.slice(baseAt));
  return out;
}

export function resolveConflict(
  block: ConflictBlock,
  pick: MergePick,
): ConflictBlock {
  const lines =
    pick === "ours"
      ? block.oursLines
      : pick === "theirs"
        ? block.theirsLines
        : [...block.oursLines, ...block.theirsLines];
  return {
    ...block,
    resolution: pick,
    lines,
    wordSegs: pick === "both" ? null : block.wordSegs,
    wordSegsTheirs: pick === "both" ? null : block.wordSegsTheirs,
  };
}

export function ignoreConflict(block: ConflictBlock): ConflictBlock {
  return { ...block, resolution: "ignored" };
}

export function setSideState(block: SideBlock, state: "applied" | "ignored"): SideBlock {
  return { ...block, state };
}

/** 冲突块当前展示的行来自哪一侧；手改 / 忽略 / 两边都留返回 null。 */
export function conflictSide(block: ConflictBlock): "ours" | "theirs" | null {
  if (block.resolution === "ours") return "ours";
  if (block.resolution === "theirs") return "theirs";
  return null;
}

export function isUnresolved(block: MergeBlock): boolean {
  return block.kind === "conflict" && block.resolution === "pending";
}

export function isChangeChunk(block: MergeBlock): boolean {
  return block.kind !== "equal";
}

/** 结果稿行号 → 块下标，以及每块在结果稿里的起始行。 */
export type ResultLayout = {
  lines: string[];
  lineBlock: number[];
  blockStart: number[];
  total: number;
};

export function resultLayout(blocks: MergeBlock[]): ResultLayout {
  const lines: string[] = [];
  const lineBlock: number[] = [];
  const blockStart: number[] = [];
  blocks.forEach((block, index) => {
    const blockLines = blockResultLines(block);
    blockStart.push(lines.length);
    for (const line of blockLines) {
      lines.push(line);
      lineBlock.push(index);
    }
  });
  return { lines, lineBlock, blockStart, total: lines.length };
}

/**
 * 三栏各自的「全局行号」数组：同一块的三栏行共享一段全局区间，
 * 块的区间宽度取三栏行数的最大值，保证不同行数的块仍能跨栏对齐。
 */
export function globalLineMaps(...panes: number[][]): number[][] {
  const blockCount = panes[0]?.length ?? 0;
  const strides: number[] = [];
  for (let i = 0; i < blockCount; i++) {
    strides.push(Math.max(1, ...panes.map((counts) => counts[i] ?? 0)));
  }
  return panes.map((counts) => {
    const out: number[] = [];
    let g = 0;
    for (let i = 0; i < counts.length; i++) {
      for (let line = 0; line < counts[i]; line++) out.push(g + line);
      g += strides[i];
    }
    return out;
  });
}

export function closestLineToGlobal(map: number[], target: number): number {
  if (!map.length) return 0;
  let lo = 0;
  let hi = map.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (map[mid] < target) lo = mid + 1;
    else hi = mid;
  }
  if (lo > 0 && Math.abs(map[lo - 1] - target) <= Math.abs(map[lo] - target)) {
    return lo - 1;
  }
  return lo;
}

/**
 * 结果稿的手工编辑回到块模型：找出受影响行区间，把涉及的块并成一个
 * custom 块（编辑落在冲突块内则该块转 custom，不再算待定）。
 */
export function applyResultEdit(
  blocks: MergeBlock[],
  layout: ResultLayout,
  nextLines: string[],
): MergeBlock[] {
  const prevLines = layout.lines;
  let start = 0;
  const limit = Math.min(prevLines.length, nextLines.length);
  while (start < limit && prevLines[start] === nextLines[start]) start += 1;
  let prevEnd = prevLines.length;
  let nextEnd = nextLines.length;
  while (
    prevEnd > start &&
    nextEnd > start &&
    prevLines[prevEnd - 1] === nextLines[nextEnd - 1]
  ) {
    prevEnd -= 1;
    nextEnd -= 1;
  }
  if (prevEnd === start && nextEnd === start) return blocks;
  if (!blocks.length) {
    return [
      {
        id: 0,
        kind: "custom",
        lines: nextLines.slice(start, nextEnd),
        oursRange: emptyRange(0),
        theirsRange: emptyRange(0),
      },
    ];
  }

  const firstBlock =
    start < layout.lineBlock.length ? layout.lineBlock[start] : blocks.length - 1;
  const lastBlock =
    prevEnd > start
      ? layout.lineBlock[Math.min(prevEnd, layout.lineBlock.length) - 1]
      : firstBlock;

  const firstStart = layout.blockStart[firstBlock];
  const lastEnd =
    layout.blockStart[lastBlock] + blockResultLines(blocks[lastBlock]).length;
  const mergedLines = [
    ...layout.lines.slice(firstStart, start),
    ...nextLines.slice(start, nextEnd),
    ...layout.lines.slice(prevEnd, lastEnd),
  ];

  const out: MergeBlock[] = [];
  let id = 0;
  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i];
    if (i < firstBlock || i > lastBlock) {
      out.push({ ...block, id: id++ });
      continue;
    }
    if (i === firstBlock) {
      out.push({
        id: id++,
        kind: "custom",
        lines: mergedLines,
        oursRange: emptyRange(block.oursRange.start),
        theirsRange: emptyRange(block.theirsRange.start),
      });
    }
  }
  return out;
}

/** 结果稿落盘时保持与原文一致的结尾换行习惯。 */
export function withDocumentEnding(text: string, reference: string): string {
  if (!text) return text;
  const wantsNl = reference.endsWith("\n");
  const hasNl = text.endsWith("\n");
  if (wantsNl && !hasNl) return `${text}\n`;
  if (!wantsNl && hasNl) return text.replace(/\n$/, "");
  return text;
}

export function chunkTitle(block: MergeBlock): string {
  if (block.kind === "conflict") {
    const heading = headingOf(block.oursLines) || headingOf(block.theirsLines);
    if (heading) return heading;
    const line = firstMeaningful(block.oursLines) || firstMeaningful(block.theirsLines);
    return line || "两边都改了这一段";
  }
  if (block.kind === "side") {
    const heading = headingOf(block.lines) || headingOf(block.baseLines);
    if (heading) return heading;
    return firstMeaningful(block.lines) || firstMeaningful(block.baseLines) || "改动";
  }
  if (block.kind === "custom") {
    return firstMeaningful(block.lines) || "手工修改";
  }
  return "";
}

function headingOf(lines: string[]): string {
  for (const line of lines) {
    const trimmed = line.trim();
    if (/^#{1,3}\s+/.test(trimmed)) {
      return trimmed
        .replace(/^#{1,6}\s+/, "")
        .replace(/^[一二三四五六七八九十]+、/, "");
    }
  }
  return "";
}

function firstMeaningful(lines: string[]): string {
  const line = lines.find((item) => item.trim().length > 0);
  return line ? line.trim().slice(0, 24) : "";
}
