import { useEffect, useRef, type RefObject } from "react";

/** 在 active 时点击 ref 外关闭，可选 Escape。 */
export function useDismissOnOutsideClick(
  ref: RefObject<HTMLElement | null>,
  active: boolean,
  onDismiss: () => void,
  options?: { escape?: boolean },
) {
  const onDismissRef = useRef(onDismiss);
  onDismissRef.current = onDismiss;
  const escape = options?.escape ?? false;

  useEffect(() => {
    if (!active) return;
    function onDocClick(e: MouseEvent) {
      if (ref.current?.contains(e.target as Node)) return;
      onDismissRef.current();
    }
    function onKey(e: KeyboardEvent) {
      if (escape && e.key === "Escape") onDismissRef.current();
    }
    document.addEventListener("click", onDocClick);
    if (escape) document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onDocClick);
      if (escape) document.removeEventListener("keydown", onKey);
    };
  }, [active, escape, ref]);
}
