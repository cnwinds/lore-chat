import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";
import type { ChatMessage, DocContextItem } from "../../api";
import { isStreamingForView, type StreamOwnership } from "./streamOwnership";
import {
  TurnObservationEngine,
  type DocContext,
  type StreamEndInfo,
} from "./turnObservationClient";

export type { DocContext, StreamEndInfo } from "./turnObservationClient";

type UseAgentStreamOptions = {
  conversationId: string | null;
  previewPath?: string | null;
  webEnabled: boolean;
  docContextItems: DocContextItem[];
  primaryDocPath: string | null;
  msgs: ChatMessage[];
  setMsgs: Dispatch<SetStateAction<ChatMessage[]>>;
  setSummarized: Dispatch<SetStateAction<boolean>>;
  setSummaryPath: Dispatch<SetStateAction<string | null>>;
  conversationIdRef: MutableRefObject<string | null>;
  skipLoadRef: MutableRefObject<string | null>;
  streamOwnership: StreamOwnership;
  stickToBottomRef: MutableRefObject<boolean>;
  onConversationCreated?: (id: string) => void;
  onFirstQuestionTitle?: (id: string, title: string) => void;
  onSidebarRefresh?: () => void;
  onKbChanged?: (changedPath?: string) => void;
  onStreamEnd?: (info: StreamEndInfo) => void;
  onInjectDeferred?: (injectId: string) => void;
  onUserInjected?: (injectId: string) => void;
};

export function useAgentStream({
  conversationId,
  webEnabled,
  docContextItems,
  primaryDocPath,
  msgs,
  setMsgs,
  setSummarized,
  setSummaryPath,
  conversationIdRef,
  skipLoadRef,
  streamOwnership,
  stickToBottomRef,
  onConversationCreated,
  onFirstQuestionTitle,
  onSidebarRefresh,
  onKbChanged,
  onStreamEnd,
  onInjectDeferred,
  onUserInjected,
}: UseAgentStreamOptions) {
  const { streamingRef } = streamOwnership;
  const [streaming, setStreaming] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [streamViewId, setStreamViewId] = useState<string | null>(null);
  const [liveElapsedMs, setLiveElapsedMs] = useState(0);
  const [streamNowMs, setStreamNowMs] = useState(() => Date.now());
  const streamingStartRef = useRef<number | null>(null);
  const streamingAssistantIdxRef = useRef<number | null>(null);
  const conversationIdPropRef = useRef(conversationId);
  conversationIdPropRef.current = conversationId;

  const onStreamEndRef = useRef(onStreamEnd);
  const onInjectDeferredRef = useRef(onInjectDeferred);
  const onUserInjectedRef = useRef(onUserInjected);
  onStreamEndRef.current = onStreamEnd;
  onInjectDeferredRef.current = onInjectDeferred;
  onUserInjectedRef.current = onUserInjected;

  const engineRef = useRef<TurnObservationEngine | null>(null);
  if (!engineRef.current) {
    engineRef.current = new TurnObservationEngine(
      streamOwnership,
      {
        getViewConversationId: () => conversationIdRef.current,
        patchMsgs: (updater) => setMsgs(updater),
        setSummarized,
        setSummaryPath,
        onStreamingChange: setStreaming,
        onStreamViewIdChange: setStreamViewId,
        onReconcilingChange: setReconciling,
        onStreamStartMs: (ms) => {
          streamingStartRef.current = ms;
          if (ms !== null) {
            setLiveElapsedMs(Math.max(0, Date.now() - ms));
          }
        },
        onConversationCreated,
        onFirstQuestionTitle,
        onSidebarRefresh,
        onKbChanged,
        onStreamEnd: (info) => onStreamEndRef.current?.(info),
        onInjectDeferred: (id) => onInjectDeferredRef.current?.(id),
        onUserInjected: (id) => onUserInjectedRef.current?.(id),
      },
      {
        getConversationIdProp: () => conversationIdPropRef.current,
        conversationIdRef,
        skipLoadRef,
        stickToBottomRef,
        streamingAssistantIdxRef,
      },
    );
  }
  const engine = engineRef.current;

  useEffect(() => {
    streamingRef.current = streaming;
    if (!streaming) {
      streamingStartRef.current = null;
      streamingAssistantIdxRef.current = null;
      return;
    }
    const tick = () => {
      const now = Date.now();
      setStreamNowMs(now);
      if (streamingStartRef.current !== null) {
        setLiveElapsedMs(now - streamingStartRef.current);
      }
    };
    tick();
    const id = window.setInterval(tick, 100);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streaming]);

  useEffect(() => {
    if (!conversationId) return;
    return () => engine.detachObservation();
  }, [conversationId, engine]);

  function resolveDocContext(): DocContext {
    return {
      trayPaths: docContextItems.map((d) => d.path),
      docContext: docContextItems,
      primary: primaryDocPath,
    };
  }

  const runAgentStream = useMemo(
    () =>
      async (
        apiText: string,
        userDisplayText?: string,
        userMeta?: Pick<
          ChatMessage,
          "attachments" | "doc_context" | "primary_doc"
        >,
        docCtx?: DocContext,
        opts?: {
          webEnabled?: boolean;
          reuseUserMessageId?: string;
          replaceAssistantIndex?: number;
        },
      ): Promise<boolean> =>
        engine.runAgentStream(
          apiText,
          {
            webEnabled,
            msgs,
            conversationId: conversationIdPropRef.current,
            docCtx: docCtx ?? resolveDocContext(),
          },
          userDisplayText,
          userMeta,
          opts,
        ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [engine, webEnabled, msgs, conversationId, docContextItems, primaryDocPath],
  );

  const resumeActiveTurn = useMemo(
    () => (cid: string, startedAt?: string | null) =>
      engine.resumeActiveTurn(cid, startedAt),
    [engine],
  );

  const stopStreaming = useMemo(
    () => () => engine.stopStreaming(),
    [engine],
  );

  const ensureConversationId = useMemo(
    () => () => engine.ensureConversationId(),
    [engine],
  );

  const streamingForView = isStreamingForView(
    streaming,
    streamViewId,
    conversationId,
  );

  return {
    streaming,
    streamingForView,
    reconciling,
    liveElapsedMs,
    streamNowMs,
    streamingAssistantIdxRef,
    streamingRef,
    runAgentStream,
    resumeActiveTurn,
    stopStreaming,
    ensureConversationId,
    resolveDocContext,
  };
}
