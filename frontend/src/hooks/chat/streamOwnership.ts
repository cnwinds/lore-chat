import type { MutableRefObject } from "react";

/** In-flight agent observation ownership shared by Chat hooks. */
export type StreamOwnership = {
  streamingRef: MutableRefObject<boolean>;
  /** Conversation that owns the in-flight stream (if any). */
  streamConversationIdRef: MutableRefObject<string | null>;
  /** Conversation the current `msgs` belong to (for history-load races). */
  msgsConversationIdRef: MutableRefObject<string | null>;
};

export function createStreamOwnership(): StreamOwnership {
  return {
    streamingRef: { current: false },
    streamConversationIdRef: { current: null },
    msgsConversationIdRef: { current: null },
  };
}

/** Skip applying history when it would clobber in-flight optimistic UI for this chat. */
export function shouldProtectStreamingHistory(
  ownership: StreamOwnership,
  loadedFor: string,
): boolean {
  return (
    ownership.streamingRef.current &&
    ownership.streamConversationIdRef.current === loadedFor &&
    ownership.msgsConversationIdRef.current === loadedFor
  );
}

/** Whether the in-flight stream should drive UI for the conversation being viewed. */
export function isStreamingForView(
  streaming: boolean,
  streamConversationId: string | null,
  viewConversationId: string | null,
): boolean {
  if (!streaming) return false;
  // First send: ids are still null until createConversation resolves.
  if (streamConversationId == null && viewConversationId == null) return true;
  return streamConversationId === viewConversationId;
}

/** Whether an in-flight stream may mutate msgs or run post-stream UI for the viewed chat. */
export function shouldPaintStreamPatch(
  ownership: StreamOwnership,
  streamCid: string | null,
  viewConversationId: string | null,
): boolean {
  if (!streamCid) return true;
  if (viewConversationId !== streamCid) return false;
  const msgsCid = ownership.msgsConversationIdRef.current;
  return msgsCid == null || msgsCid === streamCid;
}
