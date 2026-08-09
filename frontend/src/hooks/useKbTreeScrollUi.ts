import { useEffect, useRef, useState, type RefObject } from "react";
import { loadKbTreeUi, saveKbTreeScrollTop } from "../utils/kbTreeUiStorage";

type Options = {
  collapsed: boolean;
  /** 目录树已有内容，滚动容器可挂载 */
  scrollEnabled: boolean;
};

/**
 * 知识库目录滚动：防抖持久化（卸载 flush）+ 展开就绪后恢复。
 */
export function useKbTreeScrollUi(
  scrollRef: RefObject<HTMLElement | null>,
  { collapsed, scrollEnabled }: Options,
) {
  const pendingRestoreRef = useRef(true);
  const [expandReady, setExpandReady] = useState(false);

  useEffect(() => {
    if (collapsed) {
      pendingRestoreRef.current = true;
      setExpandReady(false);
    }
  }, [collapsed]);

  useEffect(() => {
    if (collapsed || !scrollEnabled) return;
    const el = scrollRef.current;
    if (!el) return;

    let timer: ReturnType<typeof setTimeout> | undefined;
    const onScroll = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        saveKbTreeScrollTop(el.scrollTop);
      }, 120);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      if (timer) clearTimeout(timer);
      saveKbTreeScrollTop(el.scrollTop);
      el.removeEventListener("scroll", onScroll);
    };
  }, [collapsed, scrollEnabled, scrollRef]);

  useEffect(() => {
    if (collapsed || !expandReady || !pendingRestoreRef.current) return;
    const el = scrollRef.current;
    if (!el) return;

    const storedTop = loadKbTreeUi()?.scrollTop;
    if (storedTop == null || storedTop <= 0) {
      pendingRestoreRef.current = false;
      return;
    }

    const raf = requestAnimationFrame(() => {
      el.scrollTop = storedTop;
      pendingRestoreRef.current = false;
    });
    return () => cancelAnimationFrame(raf);
  }, [collapsed, expandReady, scrollRef]);

  return {
    onExpandReady: () => setExpandReady(true),
  };
}
