import { useCallback, useRef, useState, type PointerEvent } from "react";
import {
  clampLeftSidebarWidth,
  isLeftSidebarIconOnly,
  persistLeftSidebarWidth,
  readLeftSidebarWidth,
} from "../utils/leftSidebarWidth";

export function useLeftSidebarWidth() {
  const [width, setWidth] = useState(readLeftSidebarWidth);
  const [dragging, setDragging] = useState(false);
  const widthRef = useRef(width);
  widthRef.current = width;

  const onPointerDown = useCallback((e: PointerEvent<HTMLElement>) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    setDragging(true);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  const onPointerMove = useCallback((e: PointerEvent<HTMLElement>) => {
    if (!e.currentTarget.hasPointerCapture(e.pointerId)) return;
    const next = clampLeftSidebarWidth(e.clientX);
    widthRef.current = next;
    setWidth(next);
  }, []);

  const onPointerUp = useCallback((e: PointerEvent<HTMLElement>) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    setDragging(false);
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    persistLeftSidebarWidth(widthRef.current);
  }, []);

  return {
    width,
    dragging,
    iconOnly: isLeftSidebarIconOnly(width),
    onPointerDown,
    onPointerMove,
    onPointerUp,
  };
}
