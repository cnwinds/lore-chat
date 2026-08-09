import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type RefObject,
} from "react";
import { loadKbTreeUi, saveKbTreeScrollTop } from "../utils/kbTreeUiStorage";

type Options = {
  collapsed: boolean;
  /** 目录树已有内容，滚动容器可挂载 */
  scrollEnabled: boolean;
};

const RESTORE_MAX_FRAMES = 12;

/**
 * 知识库目录滚动：防抖持久化 + 展开就绪后恢复。
 *
 * 恢复完成前、以及用户尚未亲手滚动前，不写回 scrollTop，
 * 避免用 0 / 夹紧后的偏小值冲掉已持久化位置。
 */
export function useKbTreeScrollUi(
  scrollRef: RefObject<HTMLElement | null>,
  { collapsed, scrollEnabled }: Options,
) {
  const pendingRestoreRef = useRef(true);
  const restoringRef = useRef(false);
  /** 仅用户滚动（非程序恢复）后才允许落盘 */
  const allowPersistRef = useRef(false);
  const [expandReady, setExpandReady] = useState(false);

  const onExpandReady = useCallback(() => {
    setExpandReady(true);
  }, []);

  useEffect(() => {
    if (collapsed) {
      pendingRestoreRef.current = true;
      restoringRef.current = false;
      allowPersistRef.current = false;
      setExpandReady(false);
    }
  }, [collapsed]);

  useEffect(() => {
    if (collapsed || !scrollEnabled) return;
    const el = scrollRef.current;
    if (!el) return;

    let timer: ReturnType<typeof setTimeout> | undefined;
    const persist = () => {
      if (
        pendingRestoreRef.current ||
        restoringRef.current ||
        !allowPersistRef.current
      ) {
        return;
      }
      saveKbTreeScrollTop(el.scrollTop);
    };
    const onScroll = () => {
      // 程序化恢复触发的 scroll 忽略；之后的才算用户滚动
      if (pendingRestoreRef.current || restoringRef.current) return;
      allowPersistRef.current = true;
      if (timer) clearTimeout(timer);
      timer = setTimeout(persist, 120);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      if (timer) clearTimeout(timer);
      persist();
      el.removeEventListener("scroll", onScroll);
    };
  }, [collapsed, scrollEnabled, scrollRef]);

  useLayoutEffect(() => {
    if (collapsed || !expandReady || !pendingRestoreRef.current) return;
    const el = scrollRef.current;
    if (!el) return;

    const storedTop = loadKbTreeUi()?.scrollTop;
    if (storedTop == null || storedTop <= 0) {
      pendingRestoreRef.current = false;
      restoringRef.current = false;
      return;
    }

    let cancelled = false;
    let frames = 0;
    restoringRef.current = true;
    allowPersistRef.current = false;

    const finish = (top: number) => {
      el.scrollTop = top;
      pendingRestoreRef.current = false;
      restoringRef.current = false;
    };

    const tryRestore = () => {
      if (cancelled) return;
      frames += 1;
      const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight);
      if (maxScroll >= storedTop) {
        finish(storedTop);
        return;
      }
      if (frames >= RESTORE_MAX_FRAMES) {
        // 尽力露出；不落盘，避免把夹紧后的偏小值写入 storage
        finish(maxScroll);
        return;
      }
      requestAnimationFrame(tryRestore);
    };

    requestAnimationFrame(tryRestore);
    return () => {
      cancelled = true;
      restoringRef.current = false;
    };
  }, [collapsed, expandReady, scrollRef]);

  return { onExpandReady };
}
