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

/** 恢复阶段：pending → restoring → idle */
type RestorePhase = "pending" | "restoring" | "idle";

const RESTORE_TIMEOUT_MS = 2000;

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
  const phaseRef = useRef<RestorePhase>("pending");
  /** 仅用户滚动（非程序恢复）后才允许落盘 */
  const allowPersistRef = useRef(false);
  const [expandReady, setExpandReady] = useState(false);

  const onExpandReady = useCallback(() => {
    setExpandReady(true);
  }, []);

  useEffect(() => {
    if (collapsed) {
      phaseRef.current = "pending";
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
      if (phaseRef.current !== "idle" || !allowPersistRef.current) return;
      saveKbTreeScrollTop(el.scrollTop);
    };
    const onScroll = () => {
      // 程序化恢复触发的 scroll 忽略；idle 之后的才算用户滚动
      if (phaseRef.current !== "idle") return;
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
    if (collapsed || !expandReady || phaseRef.current !== "pending") return;
    const el = scrollRef.current;
    if (!el) return;

    const storedTop = loadKbTreeUi()?.scrollTop;
    if (storedTop == null || storedTop <= 0) {
      phaseRef.current = "idle";
      return;
    }

    let cancelled = false;
    phaseRef.current = "restoring";
    allowPersistRef.current = false;
    const startedAt = performance.now();

    const finish = (top: number) => {
      if (cancelled || phaseRef.current !== "restoring") return;
      el.scrollTop = top;
      phaseRef.current = "idle";
    };

    const tryApply = (): boolean => {
      if (cancelled || phaseRef.current !== "restoring") return true;
      const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight);
      if (maxScroll >= storedTop) {
        finish(storedTop);
        return true;
      }
      return false;
    };

    if (tryApply()) return;

    const ro =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => {
            if (tryApply()) ro?.disconnect();
          })
        : null;
    ro?.observe(el);

    const tick = () => {
      if (cancelled || phaseRef.current !== "restoring") {
        ro?.disconnect();
        return;
      }
      if (tryApply()) {
        ro?.disconnect();
        return;
      }
      if (performance.now() - startedAt >= RESTORE_TIMEOUT_MS) {
        // 尽力露出；不落盘（allowPersist 仍为 false）
        finish(Math.max(0, el.scrollHeight - el.clientHeight));
        ro?.disconnect();
        return;
      }
      requestAnimationFrame(tick);
    };

    requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      ro?.disconnect();
      if (phaseRef.current === "restoring") {
        phaseRef.current = "pending";
      }
    };
  }, [collapsed, expandReady, scrollRef]);

  return { onExpandReady };
}
