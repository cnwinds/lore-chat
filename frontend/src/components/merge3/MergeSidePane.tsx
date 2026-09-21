import { useMemo, type RefObject } from "react";
import {
  conflictSide,
  type MergeBlock,
  type PaneRow,
} from "../../utils/mergeModel";
import { MERGE_LINE_HEIGHT, MERGE_PAD_Y } from "./constants";
import { segsToSpans } from "./lineMeta";

type Props = {
  side: "ours" | "theirs";
  title: string;
  rows: PaneRow[];
  blocks: MergeBlock[];
  activeChunkId: number | null;
  scrollerRef: RefObject<HTMLDivElement | null>;
  moverRef: RefObject<HTMLDivElement | null>;
  onSelectChunk: (chunkId: number) => void;
  onApplyChunk: (chunkId: number, side: "ours" | "theirs") => void;
  onIgnoreChunk: (chunkId: number) => void;
};

export function MergeSidePane({
  side,
  title,
  rows,
  blocks,
  activeChunkId,
  scrollerRef,
  moverRef,
  onSelectChunk,
  onApplyChunk,
  onIgnoreChunk,
}: Props) {
  const chunkButtons = useMemo(
    () => chunkButtonsFor(side, blocks),
    [side, blocks],
  );

  return (
    <section
      className={`merge3-col merge3-col--${side}`}
      aria-label={`${title}，只读`}
    >
      <header className="merge3-col-head">
        <strong>{title}</strong>
      </header>
      <div className="merge3-pane">
        <div className="merge3-scroller" ref={scrollerRef} data-pane={side}>
          <div className="merge3-row">
            <div className="merge3-gutter" aria-hidden>
              {rows.map((row, i) => (
                <div key={i} className={`merge3-ln${row.tone ? ` tone-${row.tone}` : ""}`}>
                  {i + 1}
                </div>
              ))}
            </div>
            <pre className="merge3-doc">
              {rows.map((row, i) => {
                const classes = ["merge3-line"];
                if (row.tone) classes.push(`tone-${row.tone}`);
                if (row.chunkId != null && row.chunkId === activeChunkId) {
                  classes.push("is-active");
                }
                return (
                  <div
                    key={i}
                    className={classes.join(" ")}
                    role={row.clickable ? "button" : undefined}
                    tabIndex={row.clickable ? 0 : undefined}
                    onClick={
                      row.clickable ? () => onSelectChunk(row.chunkId!) : undefined
                    }
                    onKeyDown={
                      row.clickable
                        ? (e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              onSelectChunk(row.chunkId!);
                            }
                          }
                        : undefined
                    }
                  >
                    <span className="merge3-line-text">
                      {row.segs ? segsToSpans(row.segs) : row.text || "\u200b"}
                    </span>
                  </div>
                );
              })}
            </pre>
          </div>
        </div>
        <div className="merge3-btn-layer">
          <div className="merge3-btn-mover" ref={moverRef}>
            {chunkButtons.map((btn) => (
              <div
                key={btn.chunkId}
                className="merge3-chunk-btns"
                style={{ top: btn.top }}
              >
                {btn.actions.map((action) => (
                  <button
                    key={action.key}
                    type="button"
                    className={`merge3-chunk-btn${action.tone ? ` is-${action.tone}` : ""}`}
                    title={action.title}
                    aria-label={action.title}
                    onClick={() => {
                      if (action.kind === "apply") onApplyChunk(btn.chunkId, side);
                      else onIgnoreChunk(btn.chunkId);
                    }}
                  >
                    {action.glyph}
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

type SideChunkAction = {
  key: string;
  kind: "apply" | "ignore";
  glyph: string;
  title: string;
  tone?: "apply" | "ignore";
};

function chunkButtonsFor(
  side: "ours" | "theirs",
  blocks: MergeBlock[],
) {
  const out: Array<{ chunkId: number; top: number; actions: SideChunkAction[] }> = [];
  const arrow = side === "ours" ? "»" : "«";
  blocks.forEach((block) => {
    const range = side === "ours" ? block.oursRange : block.theirsRange;
    if (range.end <= range.start && block.kind !== "conflict") return;
    const actions: SideChunkAction[] = [];
    if (block.kind === "side") {
      if (block.side !== side) return;
      if (block.state === "applied") {
        actions.push({
          key: "ignore",
          kind: "ignore",
          glyph: "✕",
          title: "这块不采用",
          tone: "ignore",
        });
      } else {
        actions.push({
          key: "apply",
          kind: "apply",
          glyph: arrow,
          title: side === "ours" ? "采用现行这一段" : "采用官方这一段",
          tone: "apply",
        });
      }
    } else if (block.kind === "conflict") {
      const shown = conflictSide(block);
      if (shown !== side) {
        actions.push({
          key: "apply",
          kind: "apply",
          glyph: arrow,
          title: side === "ours" ? "用现行" : "用官方",
          tone: "apply",
        });
      }
    } else {
      return;
    }
    if (!actions.length) return;
    out.push({
      chunkId: block.id,
      top: range.start * MERGE_LINE_HEIGHT + MERGE_PAD_Y,
      actions,
    });
  });
  return out;
}
