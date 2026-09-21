import { useLayoutEffect, useMemo, useRef, type RefObject } from "react";
import {
  type MergeBlock,
  type MergePick,
  type PaneFillers,
  type PaneRow,
  type ResultLayout,
} from "../../utils/mergeModel";
import { MERGE_LINE_HEIGHT, MERGE_PAD_Y } from "./constants";
import { segsToSpans } from "./lineMeta";

type Props = {
  value: string;
  rows: PaneRow[];
  blocks: MergeBlock[];
  layout: ResultLayout;
  fillers: PaneFillers;
  activeChunkId: number | null;
  activeTitle: string | null;
  pendingCount: number;
  scrollerRef: RefObject<HTMLDivElement | null>;
  moverRef: RefObject<HTMLDivElement | null>;
  onChange: (next: string) => void;
  onPickConflict: (chunkId: number, pick: MergePick) => void;
  onIgnoreConflict: (chunkId: number) => void;
};

export function MergeResultPane({
  value,
  rows,
  blocks,
  layout,
  fillers,
  activeChunkId,
  activeTitle,
  pendingCount,
  scrollerRef,
  moverRef,
  onChange,
  onPickConflict,
  onIgnoreConflict,
}: Props) {
  const editorRef = useRef<HTMLTextAreaElement | null>(null);

  // 每次渲染后把编辑器的内部滚动搬回外层容器，保证文字与背景层永不错位
  useLayoutEffect(() => {
    const editor = editorRef.current;
    if (!editor || (editor.scrollTop === 0 && editor.scrollLeft === 0)) return;
    const scroller = editor.closest(".merge3-scroller");
    if (scroller instanceof HTMLElement) {
      scroller.scrollTop += editor.scrollTop;
      scroller.scrollLeft += editor.scrollLeft;
    }
    editor.scrollTop = 0;
    editor.scrollLeft = 0;
  });

  const conflictButtons = useMemo(() => {
    const tops: Array<{ chunkId: number; top: number }> = [];
    blocks.forEach((block, index) => {
      if (block.kind === "conflict") {
        tops.push({
          chunkId: block.id,
          top:
            ((layout.blockStart[index] ?? 0) + fillers.offset.result[index]) *
              MERGE_LINE_HEIGHT +
            MERGE_PAD_Y,
        });
      }
    });
    return tops;
  }, [blocks, fillers, layout]);

  return (
    <section className="merge3-col merge3-col--result" aria-label="结果，可编辑">
      <header className="merge3-col-head">
        <strong>结果</strong>
        {activeTitle ? <span className="merge3-col-note">{activeTitle}</span> : null}
        {pendingCount > 0 ? (
          <span className="merge3-col-note is-pending-note">
            {pendingCount} 处待定
          </span>
        ) : null}
      </header>
      <div className="merge3-pane">
        <div className="merge3-scroller" ref={scrollerRef} data-pane="result">
          <div className="merge3-row">
            <div className="merge3-gutter" aria-hidden>
              {rows.map((row, i) => {
                const tone = row.kind === "line" ? row.tone : null;
                return (
                  <div
                    key={i}
                    className={`merge3-ln${tone ? ` tone-${tone}` : ""}`}
                  >
                    {row.kind === "line" ? contentNumber(rows, i) : ""}
                  </div>
                );
              })}
            </div>
            <div className="merge3-text">
              <pre className="merge3-backdrop" aria-hidden>
                {rows.map((row, i) => {
                  if (row.kind === "filler") {
                    return <div key={i} className="merge3-line is-filler" />;
                  }
                  const classes = ["merge3-line"];
                  if (row.tone) classes.push(`tone-${row.tone}`);
                  if (row.chunkId != null && row.chunkId === activeChunkId) {
                    classes.push("is-active");
                  }
                  return (
                    <div key={i} className={classes.join(" ")}>
                      <span className="merge3-line-text">
                        {row.segs ? segsToSpans(row.segs) : row.text || "\u200b"}
                      </span>
                    </div>
                  );
                })}
              </pre>
              <textarea
                ref={editorRef}
                className="merge3-editor"
                wrap="off"
                value={value}
                onChange={(e) => onChange(e.target.value)}
                spellCheck={false}
                aria-label="合并结果编辑"
              />
            </div>
          </div>
        </div>
        <div className="merge3-btn-layer">
          <div className="merge3-btn-mover" ref={moverRef}>
            {conflictButtons.map((btn) => (
              <div key={btn.chunkId} className="merge3-chunk-btns" style={{ top: btn.top }}>
                <button
                  type="button"
                  className="merge3-chunk-btn is-apply"
                  title="用现行"
                  aria-label="用现行"
                  onClick={() => onPickConflict(btn.chunkId, "ours")}
                >
                  «
                </button>
                <button
                  type="button"
                  className="merge3-chunk-btn is-apply"
                  title="两边都留"
                  aria-label="两边都留"
                  onClick={() => onPickConflict(btn.chunkId, "both")}
                >
                  ⇕
                </button>
                <button
                  type="button"
                  className="merge3-chunk-btn is-apply"
                  title="用官方"
                  aria-label="用官方"
                  onClick={() => onPickConflict(btn.chunkId, "theirs")}
                >
                  »
                </button>
                <button
                  type="button"
                  className="merge3-chunk-btn is-ignore"
                  title="保持现状，不再提示"
                  aria-label="忽略这一处"
                  onClick={() => onIgnoreConflict(btn.chunkId)}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

/** 行号槽只给正文行编号，填充行不占行号。 */
function contentNumber(rows: PaneRow[], index: number): string {
  let count = 0;
  for (let i = 0; i <= index; i++) {
    if (rows[i].kind === "line") count += 1;
  }
  return String(count);
}
