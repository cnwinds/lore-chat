import { useEffect, useState, type MutableRefObject } from "react";
import { getConversation, type ChatMessage } from "../../api";

type Options = {
  conversationId: string | null;
  skipLoadRef: MutableRefObject<string | null>;
  streamingRef: MutableRefObject<boolean>;
};

export function useChatConversation({
  conversationId,
  skipLoadRef,
  streamingRef,
}: Options) {
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [summarized, setSummarized] = useState(false);
  const [summaryPath, setSummaryPath] = useState<string | null>(null);

  useEffect(() => {
    if (!conversationId) {
      setMsgs([]);
      setSummarized(false);
      setSummaryPath(null);
      return;
    }
    if (skipLoadRef.current === conversationId || streamingRef.current) {
      return;
    }
    let cancelled = false;
    setLoadingHistory(true);
    getConversation(conversationId)
      .then((conv) => {
        if (!cancelled) {
          setMsgs(conv.messages);
          setSummarized(!!conv.summarized);
          setSummaryPath(conv.summary_path ?? null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMsgs([]);
          setSummarized(false);
          setSummaryPath(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  return {
    msgs,
    setMsgs,
    loadingHistory,
    summarized,
    setSummarized,
    summaryPath,
    setSummaryPath,
  };
}
