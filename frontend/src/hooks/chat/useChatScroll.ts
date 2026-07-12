import { useEffect, useLayoutEffect, useRef, type MutableRefObject } from "react";

const SCROLL_BOTTOM_THRESHOLD = 80;

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

  function scrollMessagesToBottom() {
    const el = messagesContainerRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }

  useEffect(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const handleScroll = () => {
      stickToBottomRef.current = isNearBottom(el);
    };
    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  useLayoutEffect(() => {
    if (stickToBottomRef.current) {
      scrollMessagesToBottom();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { messagesContainerRef, stickToBottomRef, scrollMessagesToBottom };
}
