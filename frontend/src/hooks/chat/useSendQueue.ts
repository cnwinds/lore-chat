import { useCallback, useEffect, useRef, useState } from "react";
import type { DocContextItem } from "../../api";
import {
  SEND_QUEUE_MAX,
  loadSendQueue,
  saveSendQueue,
  moveQueueItem,
  setGroupTiming,
  type QueueTiming,
  type SendQueueItem,
} from "../../utils/sendQueue";
import { newId } from "../../utils/id";

export function useSendQueue(conversationId: string | null) {
  const [items, setItemsState] = useState<SendQueueItem[]>(() =>
    loadSendQueue(conversationId),
  );
  /** After stop or send failure — do not auto-flush until continue. */
  const [paused, setPaused] = useState(false);
  const conversationIdRef = useRef(conversationId);

  useEffect(() => {
    conversationIdRef.current = conversationId;
    setItemsState(loadSendQueue(conversationId));
    setPaused(false);
  }, [conversationId]);

  useEffect(() => {
    saveSendQueue(conversationId, items);
  }, [conversationId, items]);

  const enqueue = useCallback(
    (partial: {
      text: string;
      timing?: QueueTiming;
      doc_context?: DocContextItem[];
      primary_doc?: string | null;
      attachments?: string[];
      webEnabled: boolean;
    }): boolean => {
      let ok = false;
      setItemsState((prev) => {
        if (prev.length >= SEND_QUEUE_MAX) {
          window.alert(`发送队列最多 ${SEND_QUEUE_MAX} 条`);
          return prev;
        }
        ok = true;
        return [
          ...prev,
          {
            id: newId(),
            text: partial.text,
            timing: partial.timing ?? "defer",
            mergeWithNext: false,
            doc_context: partial.doc_context,
            primary_doc: partial.primary_doc ?? null,
            attachments: partial.attachments,
            webEnabled: partial.webEnabled,
            locked: false,
            error: null,
          },
        ];
      });
      return ok;
    },
    [],
  );

  const updateItem = useCallback((id: string, patch: Partial<SendQueueItem>) => {
    setItemsState((prev) =>
      prev.map((item) => {
        if (item.id !== id) return item;
        if (item.locked && (patch.text !== undefined || patch.timing !== undefined)) {
          return item;
        }
        return { ...item, ...patch };
      }),
    );
  }, []);

  const setItemTiming = useCallback((id: string, timing: QueueTiming) => {
    setItemsState((prev) => {
      const idx = prev.findIndex((x) => x.id === id);
      if (idx < 0 || prev[idx].locked) return prev;
      const inGroup =
        prev[idx].mergeWithNext || (idx > 0 && prev[idx - 1].mergeWithNext);
      if (inGroup) return setGroupTiming(prev, idx, timing);
      return prev.map((x, i) =>
        i === idx ? { ...x, timing, error: null } : x,
      );
    });
  }, []);

  const removeItem = useCallback((id: string) => {
    setItemsState((prev) => {
      const target = prev.find((x) => x.id === id);
      if (!target || target.locked) return prev;
      return prev.filter((x) => x.id !== id);
    });
  }, []);

  const moveItem = useCallback((id: string, direction: -1 | 1) => {
    setItemsState((prev) => {
      const idx = prev.findIndex((x) => x.id === id);
      if (idx < 0 || prev[idx].locked) return prev;
      return moveQueueItem(prev, idx, direction);
    });
  }, []);

  const setItems = useCallback(
    (next: SendQueueItem[] | ((prev: SendQueueItem[]) => SendQueueItem[])) => {
      setItemsState((prev) => (typeof next === "function" ? next(prev) : next));
    },
    [],
  );

  const clear = useCallback(() => {
    setItemsState((prev) => prev.filter((x) => x.locked));
  }, []);

  const setAllTiming = useCallback((timing: QueueTiming) => {
    setItemsState((prev) =>
      prev.map((x) => (x.locked ? x : { ...x, timing, error: null })),
    );
  }, []);

  const setAllMerge = useCallback((merge: boolean) => {
    setItemsState((prev) =>
      prev.map((x, i) => {
        if (x.locked) return x;
        if (i === prev.length - 1) return { ...x, mergeWithNext: false };
        return { ...x, mergeWithNext: merge };
      }),
    );
  }, []);

  return {
    items,
    setItems,
    paused,
    setPaused,
    enqueue,
    updateItem,
    setItemTiming,
    removeItem,
    moveItem,
    clear,
    setAllTiming,
    setAllMerge,
  };
}
