import { useEffect, useRef, type RefObject } from "react";

/** 在 active 时点击/按下 ref 外关闭，可选 Escape（捕获阶段并 stopPropagation）。 */
export function useDismissOnOutsideClick(
  ref: RefObject<HTMLElement | null>,
  active: boolean,
  onDismiss: () => void,
  options?: { escape?: boolean; pointerEvent?: "click" | "mousedown" },
) {
  const onDismissRef = useRef(onDismiss);
  onDismissRef.current = onDismiss;
  const escape = options?.escape ?? false;
  const pointerEvent = options?.pointerEvent ?? "click";

  useEffect(() => {
    if (!active) return;
    function onPointer(e: MouseEvent) {
      if (ref.current?.contains(e.target as Node)) return;
      onDismissRef.current();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onDismissRef.current();
      }
    }
    document.addEventListener(pointerEvent, onPointer);
    if (escape) window.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener(pointerEvent, onPointer);
      if (escape) window.removeEventListener("keydown", onKey, true);
    };
  }, [active, escape, pointerEvent, ref]);
}
