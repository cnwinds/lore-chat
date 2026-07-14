import { useCallback, useEffect, useRef, useState } from "react";
import { getConversationEvents } from "../../api";

const MEMORY_EVENT_TYPES = new Set(["memory_updated", "memory_decayed"]);
const POLL_MS = 5000;

export type MemoryEventNotice = {
  id: string;
  kind: "memory_updated" | "memory_decayed";
  label: string;
};

export function memoryEventLabel(eventType: string): string | null {
  if (eventType === "memory_updated") return "已更新记忆";
  if (eventType === "memory_decayed") return "记忆已衰减";
  return null;
}

function latestMemoryEvent(
  events: Awaited<ReturnType<typeof getConversationEvents>>["events"],
) {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = events[i]!;
    if (MEMORY_EVENT_TYPES.has(event.event_type)) return event;
  }
  return null;
}

export function useConversationMemoryEvents(
  conversationId: string | null,
  options?: { pollMs?: number },
) {
  const pollMs = options?.pollMs ?? POLL_MS;
  const [notice, setNotice] = useState<MemoryEventNotice | null>(null);
  const lastEventIdRef = useRef<string | null>(null);

  const dismissNotice = useCallback(() => setNotice(null), []);

  useEffect(() => {
    if (!conversationId) {
      lastEventIdRef.current = null;
      setNotice(null);
      return;
    }

    let cancelled = false;
    let timer: number | undefined;

    async function poll(showNotices: boolean) {
      try {
        const { events } = await getConversationEvents(conversationId!, {
          afterEventId: lastEventIdRef.current,
        });
        if (cancelled || events.length === 0) return;

        lastEventIdRef.current = events[events.length - 1]!.id;
        if (!showNotices) return;

        const latest = latestMemoryEvent(events);
        if (!latest) return;
        const label = memoryEventLabel(latest.event_type);
        if (!label) return;
        setNotice({
          id: latest.id,
          kind: latest.event_type as MemoryEventNotice["kind"],
          label,
        });
      } catch {
        /* transient network errors */
      }
    }

    void (async () => {
      await poll(false);
      if (cancelled) return;
      timer = window.setInterval(() => void poll(true), pollMs);
    })();

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, [conversationId, pollMs]);

  return { notice, dismissNotice };
}
