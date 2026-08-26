import { useEffect, type RefObject } from "react";

/** 打开浮层时锁定指定滚动容器（而非 document.body）。 */
export function useScrollLock(
  enabled: boolean,
  scrollRootRef: RefObject<HTMLElement | null>,
): void {
  useEffect(() => {
    if (!enabled) return;
    const el = scrollRootRef.current;
    if (!el) return;
    const prev = el.style.overflow;
    el.style.overflow = "hidden";
    return () => {
      el.style.overflow = prev;
    };
  }, [enabled, scrollRootRef]);
}
