import { useCallback, useEffect, useRef, useState } from "react";
import type { DocContextItem } from "../../api";
import {
  getContextSendQueue,
  enqueueContextQueue,
  patchContextQueueItem,
  removeContextQueueItem,
  clearContextQueue,
  guideContextQueueItem,
  moveContextQueueItem,
  pauseContextQueue,
  type ServerSendQueueItem,
  type QueueTiming,
} from "../../api/sendQueue";
import type { SendQueueItem } from "../../utils/sendQueue";

function toClientItem(raw: ServerSendQueueItem): SendQueueItem {
  return {
    id: raw.id,
    text: raw.text,
    timing: raw.timing,
    mergeWithNext: false,
    doc_context: (raw.doc_context ?? undefined) as DocContextItem[] | undefined,
    primary_doc: raw.primary_doc ?? null,
    attachments: raw.attachments ?? undefined,
    webEnabled: !!raw.web_enabled,
    mentions: raw.mentions ?? undefined,
    locked: false,
    error: raw.error,
  };
}

const SEND_QUEUE_MAX = 20;

export function useSendQueue(conversationId: string | null) {
  const [items, setItemsState] = useState<SendQueueItem[]>([]);
  /** 服务端暂停态（发送失败/停止/征询中由服务端置位）。 */
  const [paused, setPausedState] = useState(false);
  const [loading, setLoading] = useState(false);
  const conversationIdRef = useRef(conversationId);

  const applySnapshot = useCallback(
    (snap: {
      items: import("../../api/sendQueue").ServerSendQueueItem[];
      paused: boolean;
    }) => {
      setItemsState(snap.items.map(toClientItem));
      setPausedState(snap.paused);
    },
    [],
  );

  const refresh = useCallback(async () => {
    if (!conversationIdRef.current) return;
    try {
      applySnapshot(await getContextSendQueue(conversationIdRef.current));
    } catch {
      /* 拉取失败：保留当前镜像 */
    }
  }, []);

  useEffect(() => {
    conversationIdRef.current = conversationId;
    setItemsState([]);
    setPausedState(false);
    if (!conversationId) return;
    setLoading(true);
    getContextSendQueue(conversationId)
      .then(applySnapshot)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [conversationId, applySnapshot]);

  /** 乐观更新 + 服务端收敛（以后端为准，兼顾跨端）。 */
  const mutate = useCallback(
    async (fn: () => Promise<unknown>) => {
      try {
        await fn();
      } catch {
        /* 失败保镜像，等待下次收敛 */
      }
      await refresh();
    },
    [refresh],
  );

  const enqueue = useCallback(
    (partial: {
      text: string;
      timing?: QueueTiming;
      doc_context?: DocContextItem[];
      primary_doc?: string | null;
      attachments?: string[];
      webEnabled: boolean;
      mentions?: string[];
    }): boolean => {
      if (items.length >= SEND_QUEUE_MAX) {
        window.alert(`发送队列最多 ${SEND_QUEUE_MAX} 条`);
        return false;
      }
      void mutate(() =>
        enqueueContextQueue(conversationIdRef.current || "", {
          text: partial.text,
          timing: partial.timing ?? "defer",
          doc_context: partial.doc_context,
          primary_doc: partial.primary_doc ?? undefined,
          attachments: partial.attachments,
          web_enabled: partial.webEnabled,
          mentions: partial.mentions,
        }),
      );
      return true;
    },
    [items.length, mutate],
  );

  const updateItem = useCallback(
    (id: string, patch: Partial<SendQueueItem>) => {
      void mutate(() =>
        patchContextQueueItem(conversationIdRef.current || "", id, {
          text: patch.text,
          timing: patch.timing,
        }),
      );
    },
    [],
  );

  const setItemTiming = useCallback(
    (id: string, timing: QueueTiming) => {
      void mutate(() =>
        patchContextQueueItem(conversationIdRef.current || "", id, { timing }),
      );
    },
    [],
  );

  const removeItem = useCallback(
    (id: string) => {
      void mutate(() =>
        removeContextQueueItem(conversationIdRef.current || "", id),
      );
    },
    [],
  );

  const moveItem = useCallback(
    (id: string, direction: -1 | 1) => {
      void mutate(() =>
        moveContextQueueItem(
          conversationIdRef.current || "",
          id,
          direction,
        ),
      );
    },
    [],
  );

  /** 引导：服务端移到队首并注入当前回合。 */
  const guideItem = useCallback(
    (id: string) => {
      void mutate(() =>
        guideContextQueueItem(conversationIdRef.current || "", id),
      );
    },
    [],
  );

  const setItems = useCallback(
    (next: SendQueueItem[] | ((prev: SendQueueItem[]) => SendQueueItem[])) => {
      setItemsState((prev) => (typeof next === "function" ? next(prev) : next));
    },
    [],
  );

  const clear = useCallback(() => {
    void mutate(() => clearContextQueue(conversationIdRef.current || ""));
  }, []);

  const setPaused = useCallback((value: boolean) => {
    setPausedState(value);
    void mutate(() => pauseContextQueue(conversationIdRef.current || "", value));
  }, []);

  const setAllTiming = useCallback(
    (timing: QueueTiming) => {
      for (const item of items) setItemTiming(item.id, timing);
    },
    [items, setItemTiming],
  );

  const setAllMerge = useCallback(() => {}, []);

  return {
    items,
    setItems,
    paused,
    setPaused,
    loading,
    refresh,
    enqueue,
    updateItem,
    setItemTiming,
    removeItem,
    moveItem,
    guideItem,
    clear,
    setAllTiming,
    setAllMerge,
  };
}
