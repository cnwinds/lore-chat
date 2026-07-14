import { useEffect, useRef, useState, type MutableRefObject } from "react";
import { getConversation, type ChatMessage } from "../../api";
import {
  scrollToMessageHighlight,
  type JumpTarget,
} from "./useConversationJump";

type Options = {
  conversationId: string | null;
  skipLoadRef: MutableRefObject<string | null>;
  streamingRef: MutableRefObject<boolean>;
  pendingJump?: JumpTarget | null;
  onJumpHandled?: () => void;
};

export function useChatConversation({
  conversationId,
  skipLoadRef,
  streamingRef,
  pendingJump = null,
  onJumpHandled,
}: Options) {
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [summarized, setSummarized] = useState(false);
  const [summaryPath, setSummaryPath] = useState<string | null>(null);
  const pendingJumpRef = useRef<JumpTarget | null>(null);

  useEffect(() => {
    if (pendingJump) {
      pendingJumpRef.current = pendingJump;
    }
  }, [pendingJump]);

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
        if (!cancelled && !streamingRef.current) {
          setMsgs(conv.messages);
          setSummarized(!!conv.summarized);
          setSummaryPath(conv.summary_path ?? null);
        }
      })
      .catch(() => {
        if (!cancelled && !streamingRef.current) {
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

  useEffect(() => {
    const target = pendingJumpRef.current;
    if (!target || target.conversationId !== conversationId) return;
    if (loadingHistory || msgs.length === 0) return;

    const range =
      target.startChar !== undefined && target.endChar !== undefined
        ? { start: target.startChar, end: target.endChar }
        : undefined;

    const frame = requestAnimationFrame(() => {
      const ok = scrollToMessageHighlight(
        target.messageId,
        range,
        target.offsetVersion,
      );
      if (ok) {
        pendingJumpRef.current = null;
        onJumpHandled?.();
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [conversationId, loadingHistory, msgs, onJumpHandled]);

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

export type { JumpTarget };
