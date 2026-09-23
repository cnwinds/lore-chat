import type { WordSeg } from "../../utils/mergeModel";

/** 词级差异分段渲染：变更片段加虚线下划线。 */
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
