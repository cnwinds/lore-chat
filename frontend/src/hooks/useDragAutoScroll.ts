import { useCallback, useEffect, useRef } from "react";

const EDGE_PX = 40;
const MAX_SPEED = 14;

function isTreeDragEvent(e: React.DragEvent | DragEvent): boolean {
  const dt = e.dataTransfer;
  if (!dt) return false;
  const types = dt.types;
  return (
    types.includes("Files") ||
    types.includes("text/kb-path") ||
    types.includes("text/plain")
  );
}

/** 拖放经过滚动容器边缘时自动滚动（知识库树移动/上传）。 */
export function useDragAutoScroll(
  containerRef: React.RefObject<HTMLElement | null>,
) {
  const rafRef = useRef<number | null>(null);
  const speedRef = useRef(0);

  const stop = useCallback(() => {
    speedRef.current = 0;
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const tick = useCallback(() => {
    const el = containerRef.current;
    if (!el || speedRef.current === 0) {
      rafRef.current = null;
      return;
    }
    el.scrollTop += speedRef.current;
    rafRef.current = requestAnimationFrame(tick);
  }, [containerRef]);

  const onDragOver = useCallback(
    (e: React.DragEvent | DragEvent) => {
      if (!isTreeDragEvent(e)) return;
      const el = containerRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const y = e.clientY;
      let speed = 0;
      if (y < rect.top + EDGE_PX) {
        const t = Math.min(1, (rect.top + EDGE_PX - y) / EDGE_PX);
        speed = -Math.max(4, Math.round(t * MAX_SPEED));
      } else if (y > rect.bottom - EDGE_PX) {
        const t = Math.min(1, (y - (rect.bottom - EDGE_PX)) / EDGE_PX);
        speed = Math.max(4, Math.round(t * MAX_SPEED));
      }
      speedRef.current = speed;
      if (speed !== 0 && rafRef.current === null) {
        rafRef.current = requestAnimationFrame(tick);
      }
      if (speed === 0) {
        stop();
      }
    },
    [containerRef, stop, tick],
  );

  useEffect(() => {
    document.addEventListener("dragend", stop);
    document.addEventListener("drop", stop);
    return () => {
      document.removeEventListener("dragend", stop);
      document.removeEventListener("drop", stop);
      stop();
    };
  }, [stop]);

  return { onDragOverAutoScroll: onDragOver, stopAutoScroll: stop };
}
