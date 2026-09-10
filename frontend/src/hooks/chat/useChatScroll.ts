import { useEffect, useLayoutEffect, useRef, type MutableRefObject } from "react";

/** Distance from bottom at which we still treat the view as "stuck". Keep tight so a small upward scroll unsticks. */
const SCROLL_BOTTOM_THRESHOLD = 24;

function isNearBottom(container: HTMLElement): boolean {
  const distance =
    container.scrollHeight - container.scrollTop - container.clientHeight;
  return distance <= SCROLL_BOTTOM_THRESHOLD;
}

function isMediaElement(node: EventTarget | null): boolean {
  return node instanceof HTMLImageElement || node instanceof HTMLVideoElement;
}

export function useChatScroll(
  deps: unknown[] = [],
  externalStickToBottomRef?: MutableRefObject<boolean>,
) {
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const internalStickToBottomRef = useRef(true);
  const stickToBottomRef = externalStickToBottomRef ?? internalStickToBottomRef;
  const pendingRafRef = useRef<number | null>(null);
  const programmaticRef = useRef(false);
  const touchStartYRef = useRef<number | null>(null);
  const lastScrollTopRef = useRef(0);
  const lastScrollHeightRef = useRef(0);

  function cancelPendingScroll() {
    if (pendingRafRef.current != null) {
      cancelAnimationFrame(pendingRafRef.current);
      pendingRafRef.current = null;
    }
  }

  function scrollMessagesToBottom() {
    const el = messagesContainerRef.current;
    if (!el || !stickToBottomRef.current) return;
    cancelPendingScroll();
    pendingRafRef.current = requestAnimationFrame(() => {
      pendingRafRef.current = null;
      if (!stickToBottomRef.current) return;
      programmaticRef.current = true;
      el.scrollTop = el.scrollHeight;
      lastScrollTopRef.current = el.scrollTop;
      lastScrollHeightRef.current = el.scrollHeight;
      requestAnimationFrame(() => {
        programmaticRef.current = false;
      });
    });
  }

  useEffect(() => {
    const el = messagesContainerRef.current;
    if (!el) return;

    lastScrollTopRef.current = el.scrollTop;
    lastScrollHeightRef.current = el.scrollHeight;

    const unstick = () => {
      stickToBottomRef.current = false;
      cancelPendingScroll();
    };

    const handleScroll = () => {
      if (programmaticRef.current) {
        lastScrollTopRef.current = el.scrollTop;
        lastScrollHeightRef.current = el.scrollHeight;
        return;
      }
      const prevTop = lastScrollTopRef.current;
      const prevHeight = lastScrollHeightRef.current;
      lastScrollTopRef.current = el.scrollTop;
      lastScrollHeightRef.current = el.scrollHeight;
      if (isNearBottom(el)) {
        stickToBottomRef.current = true;
        return;
      }
      const heightGrew = el.scrollHeight > prevHeight + 1;
      // 内容变高（如图片加载）时 scrollTop 往往不变，不要当成用户上翻
      const scrolledUp = el.scrollTop < prevTop - 1;
      if (scrolledUp && !heightGrew) {
        cancelPendingScroll();
        stickToBottomRef.current = false;
      }
    };

    const handleWheel = (e: WheelEvent) => {
      // deltaY < 0 → content moves down / user reads older messages
      if (e.deltaY < 0) unstick();
    };

    const handleTouchStart = (e: TouchEvent) => {
      touchStartYRef.current = e.touches[0]?.clientY ?? null;
    };

    const handleTouchMove = (e: TouchEvent) => {
      const startY = touchStartYRef.current;
      const y = e.touches[0]?.clientY;
      if (startY == null || y == null) return;
      // Finger moving down → content scrolls up (away from bottom)
      if (y - startY > 8) unstick();
    };

    const handleMediaSettle = (e: Event) => {
      if (!isMediaElement(e.target)) return;
      if (e.target instanceof Node && !el.contains(e.target)) return;
      scrollMessagesToBottom();
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    el.addEventListener("wheel", handleWheel, { passive: true });
    el.addEventListener("touchstart", handleTouchStart, { passive: true });
    el.addEventListener("touchmove", handleTouchMove, { passive: true });
    // img 的 load 不冒泡，必须捕获；视频尺寸在 loadedmetadata
    el.addEventListener("load", handleMediaSettle, true);
    el.addEventListener("error", handleMediaSettle, true);
    el.addEventListener("loadedmetadata", handleMediaSettle, true);

    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(() => {
        scrollMessagesToBottom();
      });
      const inner = el.firstElementChild;
      if (inner instanceof HTMLElement) ro.observe(inner);
    }

    return () => {
      el.removeEventListener("scroll", handleScroll);
      el.removeEventListener("wheel", handleWheel);
      el.removeEventListener("touchstart", handleTouchStart);
      el.removeEventListener("touchmove", handleTouchMove);
      el.removeEventListener("load", handleMediaSettle, true);
      el.removeEventListener("error", handleMediaSettle, true);
      el.removeEventListener("loadedmetadata", handleMediaSettle, true);
      ro?.disconnect();
      cancelPendingScroll();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useLayoutEffect(() => {
    if (stickToBottomRef.current) {
      scrollMessagesToBottom();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { messagesContainerRef, stickToBottomRef, scrollMessagesToBottom };
}
