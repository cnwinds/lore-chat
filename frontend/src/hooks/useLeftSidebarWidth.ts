import { useCallback, useRef, useState, type PointerEvent } from "react";
import {
  clampLeftSidebarRoleShare,
  clampLeftSidebarWidth,
  isLeftSidebarIconOnly,
  persistLeftSidebarRoleShare,
  persistLeftSidebarWidth,
  readLeftSidebarRoleShare,
  readLeftSidebarWidth,
} from "../utils/leftSidebarWidth";

export function useLeftSidebarWidth() {
  const [width, setWidth] = useState(readLeftSidebarWidth);
  const [roleShare, setRoleShare] = useState(readLeftSidebarRoleShare);
  const [dragging, setDragging] = useState(false);
  const [splitDragging, setSplitDragging] = useState(false);
  const widthRef = useRef(width);
  const roleShareRef = useRef(roleShare);
  const splitRef = useRef<HTMLDivElement | null>(null);
  widthRef.current = width;
  roleShareRef.current = roleShare;

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

  const onSplitPointerDown = useCallback((e: PointerEvent<HTMLElement>) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    setSplitDragging(true);
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  }, []);

  const onSplitPointerMove = useCallback((e: PointerEvent<HTMLElement>) => {
    if (!e.currentTarget.hasPointerCapture(e.pointerId)) return;
    const box = splitRef.current?.getBoundingClientRect();
    if (!box || box.height <= 0) return;
    const next = clampLeftSidebarRoleShare(
      (e.clientY - box.top) / box.height,
      box.height,
    );
    roleShareRef.current = next;
    setRoleShare(next);
  }, []);

  const onSplitPointerUp = useCallback((e: PointerEvent<HTMLElement>) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    setSplitDragging(false);
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    persistLeftSidebarRoleShare(roleShareRef.current);
  }, []);

  return {
    width,
    roleShare,
    dragging,
    splitDragging,
    iconOnly: isLeftSidebarIconOnly(width),
    splitRef,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onSplitPointerDown,
    onSplitPointerMove,
    onSplitPointerUp,
  };
}
