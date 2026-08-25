import { useEffect, useState, type RefObject } from "react";
import {
  getShareDocOutlineActiveIndex,
  type OutlineItem,
} from "../utils/docOutline";

type Options = {
  items: OutlineItem[];
  scrollRootRef: RefObject<HTMLElement | null>;
  enabled: boolean;
};

/** 分享页文档正文滚动时跟踪当前章节在大纲中的下标。 */
export function useShareDocOutlineActive({
  items,
  scrollRootRef,
  enabled,
}: Options): number {
  const [activeIndex, setActiveIndex] = useState(-1);

  useEffect(() => {
    if (!enabled || items.length === 0) {
      setActiveIndex(-1);
      return;
    }

    let raf = 0;
    const measure = () => {
      const next = getShareDocOutlineActiveIndex(scrollRootRef.current, items);
      setActiveIndex((prev) => (prev === next ? prev : next));
    };

    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(measure);
    };

    measure();

    const scrollRoot = scrollRootRef.current;
    scrollRoot?.addEventListener("scroll", onScroll, { passive: true });

    const ro =
      typeof ResizeObserver !== "undefined" && scrollRoot
        ? new ResizeObserver(onScroll)
        : null;
    if (scrollRoot) ro?.observe(scrollRoot);

    const mo =
      typeof MutationObserver !== "undefined" && scrollRoot
        ? new MutationObserver(onScroll)
        : null;
    if (scrollRoot) mo?.observe(scrollRoot, { childList: true, subtree: true });

    return () => {
      cancelAnimationFrame(raf);
      scrollRoot?.removeEventListener("scroll", onScroll);
      ro?.disconnect();
      mo?.disconnect();
    };
  }, [enabled, items, scrollRootRef]);

  return activeIndex;
}
