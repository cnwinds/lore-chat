import { useEffect, useLayoutEffect, useRef, type MutableRefObject } from "react";

/** Distance from bottom at which we still treat the view as "stuck". Keep tight so a small upward scroll unsticks. */
const SCROLL_BOTTOM_THRESHOLD = 24;

function isNearBottom(container: HTMLElement): boolean {
  const distance =
    container.scrollHeight - container.scrollTop - container.clientHeight;
  return distance <= SCROLL_BOTTOM_THRESHOLD;
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
      requestAnimationFrame(() => {
        programmaticRef.current = false;
      });
    });
  }

  useEffect(() => {
    const el = messagesContainerRef.current;
    if (!el) return;

    const unstick = () => {
      stickToBottomRef.current = false;
      cancelPendingScroll();
    };

    const handleScroll = () => {
      if (programmaticRef.current) return;
      const near = isNearBottom(el);
      if (!near) cancelPendingScroll();
      stickToBottomRef.current = near;
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

    el.addEventListener("scroll", handleScroll, { passive: true });
    el.addEventListener("wheel", handleWheel, { passive: true });
    el.addEventListener("touchstart", handleTouchStart, { passive: true });
    el.addEventListener("touchmove", handleTouchMove, { passive: true });
    return () => {
      el.removeEventListener("scroll", handleScroll);
      el.removeEventListener("wheel", handleWheel);
      el.removeEventListener("touchstart", handleTouchStart);
      el.removeEventListener("touchmove", handleTouchMove);
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
