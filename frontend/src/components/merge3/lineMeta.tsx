import type { MergeBlock, ResultLayout, WordSeg } from "../../utils/mergeModel";
import type { ChunkTone } from "./constants";

export type SideLineMeta = {
  tone: ChunkTone | null;
  chunkId: number | null;
  segs: WordSeg[] | null;
};

/** 侧栏每一行的高亮元数据：所属块、语气、词级差异分段。 */
export function sideLineMeta(
  side: "ours" | "theirs",
  lineCount: number,
  blocks: MergeBlock[],
): SideLineMeta[] {
  const meta: SideLineMeta[] = Array.from({ length: lineCount }, () => ({
    tone: null,
    chunkId: null,
    segs: null,
  }));
  for (const block of blocks) {
    const range = side === "ours" ? block.oursRange : block.theirsRange;
    if (range.end <= range.start) continue;
    let tone: ChunkTone | null = null;
    let segs: WordSeg[][] | null = null;
    if (block.kind === "side") {
      if (block.side === side) {
        tone = block.state === "applied" ? "resolved" : "ignored";
        segs = block.wordSegs;
      } else {
        tone = block.state === "applied" ? "context" : null;
      }
    } else if (block.kind === "conflict") {
      const shown = block.resolution === "ours" ? "ours" : block.resolution === "theirs" ? "theirs" : null;
      if (block.resolution === "pending") tone = "pending";
      else if (block.resolution === "both") tone = "resolved";
      else if (shown === side) tone = "resolved";
      else if (block.resolution === "custom") tone = null;
      else tone = "rejected";
      segs = side === "ours" ? block.wordSegs : block.wordSegsTheirs;
    }
    if (!tone && !segs) continue;
    for (let line = range.start; line < range.end && line < lineCount; line++) {
      meta[line] = {
        tone,
        chunkId: tone ? block.id : null,
        segs: segs ? segs[line - range.start] ?? null : null,
      };
    }
  }
  return meta;
}

export function segsToSpans(segs: WordSeg[]) {
  return segs.map((seg, i) =>
    seg.changed ? (
      <span key={i} className="merge3-word-changed">
        {seg.text}
      </span>
    ) : (
      <span key={i}>{seg.text}</span>
    ),
  );
}

type ResultLine = {
  tone: ChunkTone | null;
  chunkId: number | null;
  segs: WordSeg[] | null;
};

/** 结果稿每一行的高亮元数据（行 → 块 → 块语气 + 词级分段）。 */
export function resultLineMeta(
  blocks: MergeBlock[],
  layout: ResultLayout,
): ResultLine[] {
  const blockInfo = blocks.map((block) => {
    let tone: ChunkTone | null = null;
    let segs: WordSeg[][] | null = null;
    if (block.kind === "side") {
      tone = block.state === "applied" ? "resolved" : "ignored";
    } else if (block.kind === "conflict") {
      if (block.resolution === "pending") tone = "pending";
      else if (block.resolution === "ignored") tone = "ignored";
      else if (block.resolution === "custom") tone = null;
      else tone = "resolved";
      segs =
        block.resolution === "theirs" ? block.wordSegsTheirs : block.wordSegs;
    } else if (block.kind === "custom") {
      tone = "custom";
    }
    return { tone, segs, id: block.id };
  });
  return layout.lineBlock.map((blockIndex, lineIndex) => {
    const info = blockInfo[blockIndex];
    const localLine = lineIndex - layout.blockStart[blockIndex];
    return {
      tone: info.tone,
      chunkId: info.tone ? info.id : null,
      segs: info.segs ? info.segs[localLine] ?? null : null,
    };
  });
}
