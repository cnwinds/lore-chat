import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import {
  applyResultEdit,
  buildMergeBlocks,
  chunkTitle,
  closestLineToGlobal,
  globalLineMaps,
  ignoreConflict,
  isChangeChunk,
  isUnresolved,
  linesText,
  resolveConflict,
  resultLayout,
  resultText,
  setSideState,
  withDocumentEnding,
  type MergeBlock,
  type MergePick,
} from "../../utils/mergeModel";
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

type PaneRefs = {
  ours: RefObject<HTMLDivElement | null>;
  result: RefObject<HTMLDivElement | null>;
  theirs: RefObject<HTMLDivElement | null>;
};

type PaneBox = { el: HTMLDivElement; box: DOMRect };

function mapFor(maps: number[][], key: PaneKey): number[] {
  return key === "ours" ? maps[0] : key === "result" ? maps[1] : maps[2];
}

function visibleLines(el: HTMLDivElement): number {
  return Math.max(1, Math.floor(el.clientHeight / MERGE_LINE_HEIGHT));
}

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
  const chunks = useMemo(
    () =>
      blocks
        .map((block, index) => ({ block, index }))
        .filter(({ block }) => isChangeChunk(block))
        .map(({ block, index }) => ({
          id: block.id,
          oursLine: block.oursRange.start,
          resultLine: layout.blockStart[index],
          theirsLine: block.theirsRange.start,
        })),
    [blocks, layout],
  );
  const pendingCount = useMemo(() => blocks.filter(isUnresolved).length, [blocks]);

  const safeChunkIndex = chunks.length
    ? Math.min(chunkIndex, chunks.length - 1)
    : 0;
  const activeChunk = chunks.length ? chunks[safeChunkIndex] : null;

  const paneCounts = useMemo(
    () => ({
      ours: blocks.map((b) => b.oursRange.end - b.oursRange.start),
      result: blocks.map(resultRowLength),
      theirs: blocks.map((b) => b.theirsRange.end - b.theirsRange.start),
    }),
    [blocks],
  );
  const globalMaps = useMemo(
    () => globalLineMaps(paneCounts.ours, paneCounts.result, paneCounts.theirs),
    [paneCounts],
  );

  // ref-like 对象即可：固定身份，避免每轮渲染换引用打断回调依赖
  const scrollers = useMemo<PaneRefs>(
    () => ({ ours: { current: null }, result: { current: null }, theirs: { current: null } }),
    [],
  );
  const buttonMovers = useMemo<PaneRefs>(
    () => ({ ours: { current: null }, result: { current: null }, theirs: { current: null } }),
    [],
  );
  const tripleRef = useRef<HTMLDivElement | null>(null);
  const syncingRef = useRef(false);
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

  const centerGlobalOf = useCallback(
    (key: PaneKey) => {
      const el = scrollers[key].current;
      const map = mapFor(globalMaps, key);
      if (!el || !map.length) return 0;
      const centerLine = Math.round(
        el.scrollTop / MERGE_LINE_HEIGHT + visibleLines(el) / 2,
      );
      const clamped = Math.min(map.length - 1, Math.max(0, centerLine));
      return map[clamped];
    },
    [globalMaps, scrollers],
  );

  const alignPaneTo = useCallback(
    (key: PaneKey, globalLine: number) => {
      const el = scrollers[key].current;
      const map = mapFor(globalMaps, key);
      if (!el || !map.length) return;
      const line = closestLineToGlobal(map, globalLine);
      el.scrollTop = Math.max(
        0,
        line * MERGE_LINE_HEIGHT - (visibleLines(el) / 2 - 0.5) * MERGE_LINE_HEIGHT,
      );
    },
    [globalMaps, scrollers],
  );

  const syncFrom = useCallback(
    (key: PaneKey) => {
      if (syncingRef.current) return;
      syncingRef.current = true;
      const g = centerGlobalOf(key);
      for (const other of ["ours", "result", "theirs"] as PaneKey[]) {
        if (other !== key) alignPaneTo(other, g);
      }
      requestAnimationFrame(() => {
        syncingRef.current = false;
      });
      scheduleConnectorRedraw();
    },
    [alignPaneTo, centerGlobalOf, scheduleConnectorRedraw],
  );

  const scrollToChunk = useCallback(
    (chunk: { oursLine: number; resultLine: number; theirsLine: number } | null) => {
      if (!chunk) return;
      syncingRef.current = true;
      for (const key of ["ours", "result", "theirs"] as PaneKey[]) {
        const el = scrollers[key].current;
        if (!el) continue;
        const line =
          key === "ours"
            ? chunk.oursLine
            : key === "theirs"
              ? chunk.theirsLine
              : chunk.resultLine;
        el.scrollTop = Math.max(
          0,
          line * MERGE_LINE_HEIGHT - (visibleLines(el) / 2 - 1) * MERGE_LINE_HEIGHT,
        );
        // 不依赖 scroll 事件：同步刷新按钮层位移（隐藏环境下事件不派发）
        const mover = buttonMovers[key].current;
        if (mover) mover.style.transform = `translateY(${-el.scrollTop}px)`;
      }
      requestAnimationFrame(() => {
        syncingRef.current = false;
      });
      scheduleConnectorRedraw();
    },
    [buttonMovers, scheduleConnectorRedraw, scrollers],
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
      selectChunk(Math.min(chunks.length - 1, Math.max(0, safeChunkIndex + delta)), true);
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
        layout,
        scrollers,
        triple: tripleRef.current,
        activeId: activeChunk?.id ?? null,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [blocks, layout, connectorTick, activeChunk?.id],
  );

  const activeTitle = activeChunk
    ? chunkTitleOf(blocks, activeChunk.id)
    : null;

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
          {chunks.length} 处改动
          {pendingCount > 0 ? `，${pendingCount} 处待定` : "，没有待定"}
        </span>
      </div>
      <div className="merge3-triple" ref={tripleRef}>
        <MergeSidePane
          side="ours"
          title={oursTitle}
          text={ours}
          blocks={blocks}
          activeChunkId={activeChunk?.id ?? null}
          scrollerRef={scrollers.ours}
          moverRef={buttonMovers.ours}
          onSelectChunk={selectByChunkId}
          onApplyChunk={handleApplyChunk}
          onIgnoreChunk={handleIgnoreChunk}
        />
        <MergeResultPane
          value={resultValue}
          blocks={blocks}
          layout={layout}
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
          text={theirs}
          blocks={blocks}
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
  layout,
  scrollers,
  triple,
  activeId,
}: {
  blocks: MergeBlock[];
  layout: ReturnType<typeof resultLayout>;
  scrollers: PaneRefs;
  triple: HTMLDivElement | null;
  activeId: number | null;
}): Band[] {
  if (!triple) return [];
  const containerBox = triple.getBoundingClientRect();
  const paneBox = (key: PaneKey): PaneBox | null => {
    const el = scrollers[key].current;
    if (!el) return null;
    return { el, box: el.getBoundingClientRect() };
  };
  const oursPane = paneBox("ours");
  const resultPane = paneBox("result");
  const theirsPane = paneBox("theirs");
  if (!oursPane || !resultPane || !theirsPane) return [];

  const topIn = (pane: PaneBox, line: number) =>
    line * MERGE_LINE_HEIGHT +
    MERGE_PAD_Y -
    pane.el.scrollTop +
    (pane.box.top - containerBox.top);
  const inView = (top: number, bottom: number) =>
    bottom >= 0 && top <= containerBox.height;

  const bands: Band[] = [];
  const pushBand = (
    key: string,
    bandClass: string,
    left: { pane: PaneBox; edge: number },
    right: { pane: PaneBox; edge: number },
    leftRange: { start: number; end: number } | null,
    rightRange: { start: number; end: number } | null,
  ) => {
    if (!leftRange || !rightRange) return;
    const y1a = topIn(left.pane, leftRange.start);
    const y1b = Math.max(y1a + 3, topIn(left.pane, leftRange.end));
    const y2a = topIn(right.pane, rightRange.start);
    const y2b = Math.max(y2a + 3, topIn(right.pane, rightRange.end));
    if (!inView(y1a, y1b) && !inView(y2a, y2b)) return;
    bands.push({
      key,
      className: bandClass,
      x1: left.edge,
      x2: right.edge,
      y1a,
      y1b,
      y2a,
      y2b,
    });
  };

  const leftEdge = oursPane.box.right - containerBox.left + 1;
  const midLeft = resultPane.box.left - containerBox.left - 1;
  const midRight = resultPane.box.right - containerBox.left + 1;
  const rightEdge = theirsPane.box.left - containerBox.left - 1;

  blocks.forEach((block, index) => {
    if (block.kind === "equal") return;
    const resultRange = {
      start: layout.blockStart[index],
      end: layout.blockStart[index] + resultRowLength(block),
    };
    const className = bandClassName(block, block.id === activeId);
    const oursRange = rangeOrNull(block.oursRange);
    const theirsRange = rangeOrNull(block.theirsRange);
    pushBand(
      `lm-${block.id}`,
      className,
      { pane: oursPane, edge: leftEdge },
      { pane: resultPane, edge: midLeft },
      oursRange,
      resultRange,
    );
    pushBand(
      `mr-${block.id}`,
      className,
      { pane: resultPane, edge: midRight },
      { pane: theirsPane, edge: rightEdge },
      resultRange,
      theirsRange,
    );
  });
  return bands;
}

function rangeOrNull(range: { start: number; end: number }) {
  return range.end > range.start ? range : null;
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
