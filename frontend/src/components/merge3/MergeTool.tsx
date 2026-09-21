import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  applyResultEdit,
  buildMergeBlocks,
  chunkTitle,
  computePaneFillers,
  ignoreConflict,
  isChangeChunk,
  isUnresolved,
  linesText,
  paneContentLines,
  buildPaneRows,
  resolveConflict,
  resultLayout,
  resultText,
  setSideState,
  withDocumentEnding,
  type MergeBlock,
  type MergePick,
} from "../../utils/mergeModel";
import { scrollTopForLine } from "./geometry";
import { MERGE_LINE_HEIGHT, MERGE_PAD_Y, type PaneKey } from "./constants";
import { MergeResultPane } from "./MergeResultPane";
import { MergeSidePane } from "./MergeSidePane";

export type MergeToolHandle = {
  getResultText: () => string;
  reset: () => void;
  resolveAllConflicts: (pick: MergePick) => void;
  applyAllNonConflicting: (side?: "ours" | "theirs") => void;
};

export type MergeToolStats = { chunks: number; pending: number; empty: boolean };

type Props = {
  base: string;
  ours: string;
  theirs: string;
  oursTitle: string;
  theirsTitle: string;
  className?: string;
  footer?: ReactNode;
  onStats?: (stats: MergeToolStats) => void;
};

const PANES: PaneKey[] = ["ours", "result", "theirs"];

export const MergeTool = forwardRef<MergeToolHandle, Props>(function MergeTool(
  { base, ours, theirs, oursTitle, theirsTitle, className, footer, onStats },
  ref,
) {
  const [blocks, setBlocks] = useState<MergeBlock[]>(() =>
    buildMergeBlocks(base, ours, theirs),
  );
  const [chunkIndex, setChunkIndex] = useState(0);

  useEffect(() => {
    setBlocks(buildMergeBlocks(base, ours, theirs));
    setChunkIndex(0);
  }, [base, ours, theirs]);

  const layout = useMemo(() => resultLayout(blocks), [blocks]);
  const resultValue = useMemo(() => linesText(layout.lines), [layout]);
  const fillers = useMemo(() => computePaneFillers(blocks), [blocks]);
  const paneRows = useMemo(
    () => ({
      ours: buildPaneRows("ours", blocks, fillers),
      result: buildPaneRows("result", blocks, fillers),
      theirs: buildPaneRows("theirs", blocks, fillers),
    }),
    [blocks, fillers],
  );
  const chunks = useMemo(
    () =>
      blocks
        .map((block, index) => ({ block, index }))
        .filter(({ block }) => isChangeChunk(block))
        .map(({ block, index }) => ({
          id: block.id,
          oursVirtual: block.oursRange.start + fillers.offset.ours[index],
          resultVirtual: layout.blockStart[index] + fillers.offset.result[index],
          theirsVirtual:
            block.theirsRange.start + fillers.offset.theirs[index],
        })),
    [blocks, fillers, layout],
  );
  const pendingCount = useMemo(() => blocks.filter(isUnresolved).length, [blocks]);

  const safeChunkIndex = chunks.length
    ? Math.min(chunkIndex, chunks.length - 1)
    : 0;
  const activeChunk = chunks.length ? chunks[safeChunkIndex] : null;

  const scrollers = useMemo(
    () => ({
      ours: { current: null },
      result: { current: null },
      theirs: { current: null },
    }),
    [],
  ) as {
    ours: { current: HTMLDivElement | null };
    result: { current: HTMLDivElement | null };
    theirs: { current: HTMLDivElement | null };
  };
  const buttonMovers = useMemo(
    () => ({
      ours: { current: null },
      result: { current: null },
      theirs: { current: null },
    }),
    [],
  ) as {
    ours: { current: HTMLDivElement | null };
    result: { current: HTMLDivElement | null };
    theirs: { current: HTMLDivElement | null };
  };
  const tripleRef = useRef<HTMLDivElement | null>(null);
  // 程序化写入的 scrollTop 回执：回声事件与写入值一致时不再反向同步
  const programmaticRef = useRef(new Map<PaneKey, number>());
  const [connectorTick, setConnectorTick] = useState(0);
  const tickScheduled = useRef(false);

  const scheduleConnectorRedraw = useCallback(() => {
    if (tickScheduled.current) return;
    tickScheduled.current = true;
    requestAnimationFrame(() => {
      tickScheduled.current = false;
      setConnectorTick((t) => t + 1);
    });
  }, []);

  const syncFrom = useCallback(
    (key: PaneKey) => {
      const source = scrollers[key].current;
      if (!source) return;
      for (const other of PANES) {
        if (other === key) continue;
        const el = scrollers[other].current;
        if (!el) continue;
        const max = el.scrollHeight - el.clientHeight;
        const top = Math.min(source.scrollTop, Math.max(0, max));
        programmaticRef.current.set(other, top);
        el.scrollTop = top;
        const mover = buttonMovers[other].current;
        if (mover) mover.style.transform = `translateY(${-top}px)`;
      }
      scheduleConnectorRedraw();
    },
    [buttonMovers, scrollers, scheduleConnectorRedraw],
  );

  const scrollToChunk = useCallback(
    (
      chunk: { oursVirtual: number; resultVirtual: number; theirsVirtual: number } | null,
    ) => {
      if (!chunk) return;
      for (const key of PANES) {
        const el = scrollers[key].current;
        if (!el) continue;
        const line =
          key === "ours"
            ? chunk.oursVirtual
            : key === "theirs"
              ? chunk.theirsVirtual
              : chunk.resultVirtual;
        const top = Math.min(
          scrollTopForLine(Math.max(0, line - 2), el.clientHeight),
          Math.max(0, el.scrollHeight - el.clientHeight),
        );
        programmaticRef.current.set(key, top);
        el.scrollTop = top;
        const mover = buttonMovers[key].current;
        if (mover) mover.style.transform = `translateY(${-top}px)`;
      }
      scheduleConnectorRedraw();
    },
    [buttonMovers, scrollers, scheduleConnectorRedraw],
  );

  // 统一在捕获阶段接三栏滚动：滚动不冒泡，捕获监听可稳定命中后代元素
  useEffect(() => {
    const root = tripleRef.current;
    if (!root) return;
    const handle = (event: Event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (target.classList.contains("merge3-editor")) {
        const scroller = target.closest(".merge3-scroller");
        if (scroller instanceof HTMLElement) {
          if (target.scrollTop !== 0) {
            scroller.scrollTop += target.scrollTop;
            target.scrollTop = 0;
          }
          if (target.scrollLeft !== 0) {
            scroller.scrollLeft += target.scrollLeft;
            target.scrollLeft = 0;
          }
        }
        return;
      }
      const scroller = target.closest(".merge3-scroller");
      if (!(scroller instanceof HTMLElement)) return;
      const key = scroller.dataset.pane as PaneKey | undefined;
      if (key !== "ours" && key !== "result" && key !== "theirs") return;
      const mover = buttonMovers[key].current;
      if (mover) mover.style.transform = `translateY(${-scroller.scrollTop}px)`;
      const expected = programmaticRef.current.get(key);
      if (expected != null && Math.abs(expected - scroller.scrollTop) < 0.5) {
        programmaticRef.current.delete(key);
        return;
      }
      programmaticRef.current.delete(key);
      syncFrom(key);
    };
    root.addEventListener("scroll", handle, true);
    return () => root.removeEventListener("scroll", handle, true);
  }, [buttonMovers, syncFrom]);

  const selectChunk = useCallback(
    (next: number, scroll = false) => {
      setChunkIndex(next);
      if (scroll) scrollToChunk(chunks[next] ?? null);
    },
    [chunks, scrollToChunk],
  );

  const jump = useCallback(
    (delta: number) => {
      if (!chunks.length) return;
      selectChunk(
        Math.min(chunks.length - 1, Math.max(0, safeChunkIndex + delta)),
        true,
      );
    },
    [chunks.length, safeChunkIndex, selectChunk],
  );

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const typing =
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLInputElement;
      const prev =
        (e.key === "F8" && e.shiftKey) ||
        (e.altKey && e.key === "ArrowUp") ||
        (!typing && e.key === "[");
      const next =
        (e.key === "F8" && !e.shiftKey) ||
        (e.altKey && e.key === "ArrowDown") ||
        (!typing && e.key === "]");
      if (!prev && !next) return;
      e.preventDefault();
      jump(prev ? -1 : 1);
    }
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [jump]);

  useEffect(() => {
    scheduleConnectorRedraw();
  }, [blocks, layout, scheduleConnectorRedraw]);

  useEffect(() => {
    onStats?.({
      chunks: chunks.length,
      pending: pendingCount,
      empty: layout.total === 0 || layout.lines.every((line) => !line.trim()),
    });
  }, [chunks.length, layout, onStats, pendingCount]);

  const mutateBlock = useCallback(
    (chunkId: number, fn: (block: MergeBlock) => MergeBlock) => {
      setBlocks((prev) => prev.map((b) => (b.id === chunkId ? fn(b) : b)));
      scheduleConnectorRedraw();
    },
    [scheduleConnectorRedraw],
  );

  const handlePickConflict = useCallback(
    (chunkId: number, pick: MergePick) => {
      mutateBlock(chunkId, (b) =>
        b.kind === "conflict" ? resolveConflict(b, pick) : b,
      );
    },
    [mutateBlock],
  );

  const handleIgnoreConflict = useCallback(
    (chunkId: number) => {
      mutateBlock(chunkId, (b) =>
        b.kind === "conflict" ? ignoreConflict(b) : b,
      );
    },
    [mutateBlock],
  );

  const handleApplyChunk = useCallback(
    (chunkId: number, side: "ours" | "theirs") => {
      mutateBlock(chunkId, (b) => {
        if (b.kind === "side") return setSideState(b, "applied");
        if (b.kind === "conflict") return resolveConflict(b, side);
        return b;
      });
    },
    [mutateBlock],
  );

  const handleIgnoreChunk = useCallback(
    (chunkId: number) => {
      mutateBlock(chunkId, (b) =>
        b.kind === "side" ? setSideState(b, "ignored") : b,
      );
    },
    [mutateBlock],
  );

  const handleResultChange = useCallback((next: string) => {
    setBlocks((prev) => applyResultEdit(prev, resultLayout(prev), next.split("\n")));
  }, []);

  const resolveAllConflicts = useCallback((pick: MergePick) => {
    setBlocks((prev) =>
      prev.map((b) => (b.kind === "conflict" ? resolveConflict(b, pick) : b)),
    );
  }, []);

  const applyAllNonConflicting = useCallback((side?: "ours" | "theirs") => {
    setBlocks((prev) =>
      prev.map((b) => {
        if (b.kind !== "side") return b;
        if (side && b.side !== side) return b;
        return setSideState(b, "applied");
      }),
    );
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      getResultText: () => withDocumentEnding(resultText(blocks), theirs),
      reset: () => {
        setBlocks(buildMergeBlocks(base, ours, theirs));
        setChunkIndex(0);
      },
      resolveAllConflicts,
      applyAllNonConflicting,
    }),
    [applyAllNonConflicting, base, blocks, ours, resolveAllConflicts, theirs],
  );

  const bands = useMemo(
    () =>
      buildBands({
        blocks,
        fillers,
        layout,
        scrollers,
        triple: tripleRef.current,
        activeId: activeChunk?.id ?? null,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [blocks, fillers, layout, connectorTick, activeChunk?.id],
  );

  const activeTitle = activeChunk ? chunkTitleOf(blocks, activeChunk.id) : null;

  const selectByChunkId = useCallback(
    (chunkId: number) => {
      const at = chunks.findIndex((c) => c.id === chunkId);
      if (at >= 0) selectChunk(at);
    },
    [chunks, selectChunk],
  );

  return (
    <div className={`merge3${className ? ` ${className}` : ""}`}>
      <div className="merge3-toolbar">
        <div className="merge3-nav">
          <button
            type="button"
            className="doc-diff-btn merge3-nav-btn"
            aria-label="上一处"
            disabled={safeChunkIndex <= 0}
            onClick={() => jump(-1)}
          >
            ◀
          </button>
          <span className="merge3-nav-pos" aria-live="polite">
            {chunks.length ? `${safeChunkIndex + 1}/${chunks.length}` : "0/0"}
          </span>
          <button
            type="button"
            className="doc-diff-btn merge3-nav-btn"
            aria-label="下一处"
            disabled={chunks.length === 0 || safeChunkIndex >= chunks.length - 1}
            onClick={() => jump(1)}
          >
            ▶
          </button>
        </div>
        <div className="merge3-bulk" role="group" aria-label="应用非冲突改动">
          <span className="merge3-bulk-label">应用非冲突</span>
          <button
            type="button"
            className="doc-diff-btn"
            title="采用左方所有非冲突改动"
            onClick={() => applyAllNonConflicting("ours")}
          >
            左 »
          </button>
          <button
            type="button"
            className="doc-diff-btn"
            title="采用两方所有非冲突改动"
            onClick={() => applyAllNonConflicting()}
          >
            全部
          </button>
          <button
            type="button"
            className="doc-diff-btn"
            title="采用右方所有非冲突改动"
            onClick={() => applyAllNonConflicting("theirs")}
          >
            « 右
          </button>
        </div>
        {pendingCount > 0 ? (
          <div className="merge3-bulk" role="group" aria-label="解决全部冲突">
            <button
              type="button"
              className="doc-diff-btn"
              title="所有冲突保持现行"
              onClick={() => resolveAllConflicts("ours")}
            >
              冲突全用现行
            </button>
            <button
              type="button"
              className="doc-diff-btn"
              title="所有冲突改用官方"
              onClick={() => resolveAllConflicts("theirs")}
            >
              冲突全用官方
            </button>
          </div>
        ) : null}
        <span className="merge3-stats" aria-live="polite">
          {`${chunks.length} 处改动${pendingCount > 0 ? `，${pendingCount} 处待定` : "，没有待定"}`}
        </span>
      </div>
      <div className="merge3-triple" ref={tripleRef}>
        <MergeSidePane
          side="ours"
          title={oursTitle}
          rows={paneRows.ours}
          blocks={blocks}
          fillers={fillers}
          activeChunkId={activeChunk?.id ?? null}
          scrollerRef={scrollers.ours}
          moverRef={buttonMovers.ours}
          onSelectChunk={selectByChunkId}
          onApplyChunk={handleApplyChunk}
          onIgnoreChunk={handleIgnoreChunk}
        />
        <MergeResultPane
          value={resultValue}
          rows={paneRows.result}
          blocks={blocks}
          layout={layout}
          fillers={fillers}
          activeChunkId={activeChunk?.id ?? null}
          activeTitle={activeTitle}
          pendingCount={pendingCount}
          scrollerRef={scrollers.result}
          moverRef={buttonMovers.result}
          onChange={handleResultChange}
          onPickConflict={handlePickConflict}
          onIgnoreConflict={handleIgnoreConflict}
        />
        <MergeSidePane
          side="theirs"
          title={theirsTitle}
          rows={paneRows.theirs}
          blocks={blocks}
          fillers={fillers}
          activeChunkId={activeChunk?.id ?? null}
          scrollerRef={scrollers.theirs}
          moverRef={buttonMovers.theirs}
          onSelectChunk={selectByChunkId}
          onApplyChunk={handleApplyChunk}
          onIgnoreChunk={handleIgnoreChunk}
        />
        <svg className="merge3-connectors" aria-hidden>
          {bands.map((band) => (
            <path key={band.key} className={band.className} d={bandPath(band)} />
          ))}
        </svg>
      </div>
      {footer ? <footer className="merge3-footer">{footer}</footer> : null}
    </div>
  );
});

type PaneRefs = Record<
  PaneKey,
  { current: HTMLDivElement | null }
>;

type PaneBox = { el: HTMLDivElement; box: DOMRect };

function resultRowLength(block: MergeBlock): number {
  if (block.kind === "side" && block.state === "ignored") {
    return block.baseLines.length;
  }
  return block.lines.length;
}

function chunkTitleOf(blocks: MergeBlock[], chunkId: number): string {
  const block = blocks.find((b) => b.id === chunkId);
  if (!block) return "";
  const title = chunkTitle(block);
  if (title) return title;
  if (block.kind === "conflict") return "两边都改了这一段";
  if (block.kind === "custom") return "手工修改";
  return "";
}

function bandPath(band: Band): string {
  const mid = (band.x1 + band.x2) / 2;
  return [
    `M ${band.x1} ${band.y1a}`,
    `C ${mid} ${band.y1a}, ${mid} ${band.y2a}, ${band.x2} ${band.y2a}`,
    `L ${band.x2} ${band.y2b}`,
    `C ${mid} ${band.y2b}, ${mid} ${band.y1b}, ${band.x1} ${band.y1b}`,
    "Z",
  ].join(" ");
}

type Band = {
  key: string;
  className: string;
  x1: number;
  x2: number;
  y1a: number;
  y1b: number;
  y2a: number;
  y2b: number;
};

function buildBands({
  blocks,
  fillers,
  layout,
  scrollers,
  triple,
  activeId,
}: {
  blocks: MergeBlock[];
  fillers: ReturnType<typeof computePaneFillers>;
  layout: ReturnType<typeof resultLayout>;
  scrollers: PaneRefs;
  triple: HTMLDivElement | null;
  activeId: number | null;
}): Band[] {
  if (!triple) return [];
  const containerBox = triple.getBoundingClientRect();
  const paneBox = (key: PaneKey): { el: HTMLDivElement; box: DOMRect } | null => {
    const el = scrollers[key].current;
    if (!el) return null;
    return { el, box: el.getBoundingClientRect() };
  };
  const oursPane = paneBox("ours");
  const resultPane = paneBox("result");
  const theirsPane = paneBox("theirs");
  if (!oursPane || !resultPane || !theirsPane) return [];

  const topIn = (
    pane: PaneBox,
    scrollTop: number,
    virtualLine: number,
  ) => virtualLine * MERGE_LINE_HEIGHT + MERGE_PAD_Y - scrollTop + (pane.box.top - containerBox.top);
  const inView = (top: number, bottom: number) =>
    bottom >= 0 && top <= containerBox.height;

  const bands: Band[] = [];
  const pushBand = (
    key: string,
    bandClass: string,
    left: { pane: { el: HTMLDivElement; box: DOMRect }; edge: number; scroll: number },
    right: { pane: { el: HTMLDivElement; box: DOMRect }; edge: number; scroll: number },
    leftLine: number,
    rightLine: number,
    heightLines: number,
  ) => {
    const y1a = topIn(left.pane, left.scroll, leftLine);
    const y1b = y1a + heightLines * MERGE_LINE_HEIGHT;
    const y2a = topIn(right.pane, right.scroll, rightLine);
    const y2b = y2a + Math.max(heightLines, 1) * MERGE_LINE_HEIGHT;
    if (!inView(y1a, y1b) && !inView(y2a, y2b)) return;
    bands.push({ key, className: bandClass, x1: left.edge, x2: right.edge, y1a, y1b, y2a, y2b });
  };

  const leftEdge = oursPane.box.right - containerBox.left + 1;
  const midLeft = resultPane.box.left - containerBox.left - 1;
  const midRight = resultPane.box.right - containerBox.left + 1;
  const rightEdge = theirsPane.box.left - containerBox.left - 1;

  blocks.forEach((block, index) => {
    if (block.kind === "equal") return;
    const className = bandClassName(block, block.id === activeId);
    const oursTop = block.oursRange.start + fillers.offset.ours[index];
    const resultTop = layout.blockStart[index] + fillers.offset.result[index];
    const theirsTop = block.theirsRange.start + fillers.offset.theirs[index];
    const oursHeight = Math.max(
      1,
      block.oursRange.end - block.oursRange.start ||
        paneContentLines(block, "ours").length,
    );
    const theirsHeight = Math.max(
      1,
      block.theirsRange.end - block.theirsRange.start ||
        paneContentLines(block, "theirs").length,
    );
    const resultHeight = Math.max(
      1,
      resultRowLength(block),
    );

    pushBand(
      `lm-${block.id}`,
      className,
      { pane: oursPane, edge: leftEdge, scroll: oursPane.el.scrollTop },
      { pane: resultPane, edge: midLeft, scroll: resultPane.el.scrollTop },
      oursTop,
      resultTop,
      Math.min(oursHeight, resultHeight),
    );
    pushBand(
      `mr-${block.id}`,
      className,
      { pane: resultPane, edge: midRight, scroll: resultPane.el.scrollTop },
      { pane: theirsPane, edge: rightEdge, scroll: theirsPane.el.scrollTop },
      resultTop,
      theirsTop,
      Math.min(resultHeight, theirsHeight),
    );
  });
  return bands;
}

function bandClassName(block: MergeBlock, active: boolean): string {
  const parts = ["merge3-band"];
  if (block.kind === "side") {
    parts.push(block.state === "applied" ? "band-resolved" : "band-ignored");
  } else if (block.kind === "conflict") {
    if (block.resolution === "pending") parts.push("band-pending");
    else if (block.resolution === "ignored") parts.push("band-ignored");
    else if (block.resolution === "custom") parts.push("band-custom");
    else parts.push("band-resolved");
  } else {
    parts.push("band-custom");
  }
  if (active) parts.push("is-active");
  return parts.join(" ");
}
