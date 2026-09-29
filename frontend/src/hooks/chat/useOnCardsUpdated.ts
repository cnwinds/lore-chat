import { useEffect, useRef } from "react";
import type { MemoryEventNotice } from "./useConversationMemoryEvents";

/** 同一条 cards_updated 通知只触发一次 callback，避免父级内联回调导致重复刷新。 */
export function useOnCardsUpdated(
  notice: MemoryEventNotice | null,
  callback: (() => void) | undefined,
) {
  const callbackRef = useRef(callback);
  const handledNoticeIdRef = useRef<string | null>(null);

  callbackRef.current = callback;

  useEffect(() => {
    if (notice?.kind !== "cards_updated") return;
    if (handledNoticeIdRef.current === notice.id) return;
    handledNoticeIdRef.current = notice.id;
    callbackRef.current?.();
  }, [notice?.id, notice?.kind]);
}
