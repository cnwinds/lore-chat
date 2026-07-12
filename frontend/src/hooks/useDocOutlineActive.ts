import { useEffect, useState, type RefObject } from "react";
import {
  getPreviewOutlineActiveIndex,
  getSourceOutlineActiveIndex,
  type OutlineItem,
} from "../utils/docOutline";

type Options = {
  items: OutlineItem[];
  inSource: boolean;
  scrollRootRef: RefObject<HTMLElement | null>;
  sourceRef: RefObject<HTMLTextAreaElement | null>;
  enabled: boolean;
};

export function useDocOutlineActive({
  items,
  inSource,
  scrollRootRef,
  sourceRef,
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
      const scrollRoot = scrollRootRef.current;
      const textarea = inSource ? sourceRef.current : null;
      const next = inSource
        ? getSourceOutlineActiveIndex(textarea, items)
        : getPreviewOutlineActiveIndex(scrollRoot);
      setActiveIndex((prev) => (prev === next ? prev : next));
    };

    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(measure);
    };

    measure();

    const scrollRoot = scrollRootRef.current;
    const textarea = inSource ? sourceRef.current : null;

    scrollRoot?.addEventListener("scroll", onScroll, { passive: true });
    textarea?.addEventListener("scroll", onScroll, { passive: true });

    const ro =
      typeof ResizeObserver !== "undefined" && scrollRoot
        ? new ResizeObserver(onScroll)
        : null;
    if (scrollRoot) ro?.observe(scrollRoot);

    const mo =
      typeof MutationObserver !== "undefined" && scrollRoot && !inSource
        ? new MutationObserver(onScroll)
        : null;
    if (scrollRoot) mo?.observe(scrollRoot, { childList: true, subtree: true });

    return () => {
      cancelAnimationFrame(raf);
      scrollRoot?.removeEventListener("scroll", onScroll);
      textarea?.removeEventListener("scroll", onScroll);
      ro?.disconnect();
      mo?.disconnect();
    };
  }, [enabled, inSource, items, scrollRootRef, sourceRef]);

  return activeIndex;
}
