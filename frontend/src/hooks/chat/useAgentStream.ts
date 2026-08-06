import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";
import {
  chatStream,
  createConversation,
  getConversation,
  titleFromText,
  updateTimeline,
  KB_MUTATING_TOOLS,
  type ChatMessage,
  type DocContextItem,
  type SourceRef,
} from "../../api";
import { isInjectedUserMessage, kbPathFromToolResult, timelineAwaitsUserAnswer } from "../../utils/chatMessage";
import { nowIsoDisplay } from "../../utils/displayTime";

export type DocContext = {
  documentPaths: string[];
  docContext: DocContextItem[];
  primary: string | null;
};

export type StreamEndInfo = {
  failed: boolean;
  aborted: boolean;
  conversationId: string | null;
  /** Turn ended with an unanswered ask_user — do not auto-flush the send queue. */
  awaitingUser?: boolean;
};

type UseAgentStreamOptions = {
  conversationId: string | null;
  previewPath?: string | null;
  webEnabled: boolean;
  documentPaths: string[];
  docContextItems: DocContextItem[];
  primaryDocPath: string | null;
  msgs: ChatMessage[];
  setMsgs: Dispatch<SetStateAction<ChatMessage[]>>;
  setSummarized: Dispatch<SetStateAction<boolean>>;
  setSummaryPath: Dispatch<SetStateAction<string | null>>;
  conversationIdRef: MutableRefObject<string | null>;
  skipLoadRef: MutableRefObject<string | null>;
  streamingRef: MutableRefObject<boolean>;
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
  previewPath: _previewPath,
  webEnabled,
  documentPaths,
  docContextItems,
  primaryDocPath,
  msgs,
  setMsgs,
  setSummarized,
  setSummaryPath,
  conversationIdRef,
  skipLoadRef,
  streamingRef,
  stickToBottomRef,
  onConversationCreated,
  onFirstQuestionTitle,
  onSidebarRefresh,
  onKbChanged,
  onStreamEnd,
  onInjectDeferred,
  onUserInjected,
}: UseAgentStreamOptions) {
  const [streaming, setStreaming] = useState(false);
  const [liveElapsedMs, setLiveElapsedMs] = useState(0);
  const streamingStartRef = useRef<number | null>(null);
  const streamingAssistantIdxRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const onStreamEndRef = useRef(onStreamEnd);
  const onInjectDeferredRef = useRef(onInjectDeferred);
  const onUserInjectedRef = useRef(onUserInjected);
  onStreamEndRef.current = onStreamEnd;
  onInjectDeferredRef.current = onInjectDeferred;
  onUserInjectedRef.current = onUserInjected;

  useEffect(() => {
    streamingRef.current = streaming;
    if (!streaming) {
      streamingStartRef.current = null;
      streamingAssistantIdxRef.current = null;
      return;
    }
    const tick = () => {
      if (streamingStartRef.current !== null) {
        setLiveElapsedMs(Date.now() - streamingStartRef.current);
      }
    };
    tick();
    const id = window.setInterval(tick, 100);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streaming]);

  function resolveDocContext(): DocContext {
    return {
      documentPaths,
      docContext: docContextItems,
      primary: primaryDocPath,
    };
  }

  async function ensureConversationId(): Promise<string> {
    if (conversationId) return conversationId;
    const { id } = await createConversation();
    skipLoadRef.current = id;
    onConversationCreated?.(id);
    return id;
  }

  function stopStreaming() {
    abortRef.current?.abort();
  }

  async function runAgentStream(
    apiText: string,
    userDisplayText?: string,
    userMeta?: Pick<ChatMessage, "attachments" | "doc_context" | "primary_doc">,
    docCtx?: DocContext,
    opts?: { webEnabled?: boolean },
  ): Promise<boolean> {
    if (streamingRef.current) return false;
    const display = userDisplayText ?? apiText;
    const isFirstUserQuestion = !msgs.some((m) => m.role === "user");
    stickToBottomRef.current = true;
    streamingRef.current = true;
    setStreaming(true);
    streamingStartRef.current = Date.now();
    setLiveElapsedMs(0);

    const controller = new AbortController();
    abortRef.current = controller;

    const assistantMsg: ChatMessage = {
      role: "assistant",
      ts: nowIsoDisplay(),
      timeline: [],
      sources: [],
    };
    setMsgs((m) => {
      const assistantIdx = m.length + 1;
      streamingAssistantIdxRef.current = assistantIdx;
      return [
        ...m,
        {
          role: "user",
          text: display,
          ts: nowIsoDisplay(),
          ...(userMeta?.attachments?.length
            ? { attachments: userMeta.attachments }
            : {}),
          ...(userMeta?.doc_context?.length
            ? { doc_context: userMeta.doc_context }
            : {}),
          ...(userMeta?.primary_doc ? { primary_doc: userMeta.primary_doc } : {}),
        },
        assistantMsg,
      ];
    });
    // 流式期间助手消息始终是数组的最后一项；直接定位它，
    // 避免依赖 setMsgs 更新器里异步写入的 ref（在“继续”流程下会读到过期值，
    // 导致把 timeline 写进了 msgs[0] 这条用户消息，输出错位到右上角）。
    const patchAssistant = (updater: (msg: ChatMessage) => ChatMessage) =>
      setMsgs((prev) => {
        if (prev.length === 0) return prev;
        const idx = prev.length - 1;
        const copy = [...prev];
        copy[idx] = updater(copy[idx]);
        return copy;
      });

    let streamFailed = false;
    let aborted = false;
    let awaitingUser = false;
    let cid: string | null = null;
    try {
      cid = await ensureConversationId();
      if (isFirstUserQuestion) {
        onFirstQuestionTitle?.(cid, titleFromText(display));
      }
      const ctx = docCtx ?? resolveDocContext();
      const clientMessageId = crypto.randomUUID();
      const useWeb = opts?.webEnabled ?? webEnabled;
      for await (const { event, data } of chatStream(apiText, {
        conversationId: cid,
        activeDocPaths: ctx.documentPaths,
        docContext: ctx.docContext.length ? ctx.docContext : undefined,
        primaryDocPath: ctx.primary,
        webEnabled: useWeb,
        attachments: userMeta?.attachments ?? [],
        clientMessageId,
        signal: controller.signal,
      })) {
        if (event === "error") {
          const message = (data.message as string) || "请求失败";
          patchAssistant((msg) => ({ ...msg, text: `错误：${message}` }));
          streamFailed = true;
          break;
        }

        if (event === "user_inject") {
          const injectId = data.inject_id as string;
          patchAssistant((prevMsg) => ({
            ...prevMsg,
            timeline: updateTimeline(prevMsg.timeline ?? [], event, data),
          }));
          onUserInjectedRef.current?.(injectId);
          continue;
        }

        if (event === "inject_deferred") {
          onInjectDeferredRef.current?.(data.inject_id as string);
          continue;
        }

        patchAssistant((prevMsg) => {
          const msg = { ...prevMsg };
          if (event !== "done") {
            msg.timeline = updateTimeline(msg.timeline ?? [], event, data);
          }
          if (event === "done") {
            msg.sources = (data.sources as SourceRef[]) || [];
            if (data.total_duration_ms !== undefined) {
              msg.total_duration_ms = data.total_duration_ms as number;
            }
            msg.ts = nowIsoDisplay();
            awaitingUser = timelineAwaitsUserAnswer(msg.timeline);
          }
          return msg;
        });

        if (event === "tool_result") {
          if (
            (KB_MUTATING_TOOLS as readonly string[]).includes(
              data.tool as string,
            )
          ) {
            onKbChanged?.(kbPathFromToolResult(data));
          }
          if (
            data.tool === "ask_user" &&
            data.question_id &&
            Array.isArray(data.options) &&
            (data.options as unknown[]).length > 0
          ) {
            awaitingUser = true;
          }
        }
      }
    } catch (err) {
      if (
        (err instanceof DOMException && err.name === "AbortError") ||
        (err instanceof Error && err.name === "AbortError")
      ) {
        aborted = true;
      } else {
        streamFailed = true;
        const msg = err instanceof Error ? err.message : "请求失败";
        patchAssistant((prevMsg) => ({ ...prevMsg, text: `错误：${msg}` }));
      }
    } finally {
      abortRef.current = null;
      streamingRef.current = false;
      setStreaming(false);
      skipLoadRef.current = null;
      onSidebarRefresh?.();
      const endCid = conversationIdRef.current ?? cid;
      onStreamEndRef.current?.({
        failed: streamFailed,
        aborted,
        awaitingUser: !streamFailed && !aborted && awaitingUser,
        conversationId: endCid,
      });
      if (endCid && !streamFailed && !aborted) {
        getConversation(endCid)
          .then((conv) => {
            if (conversationIdRef.current !== endCid) return;
            // A queued follow-up turn may already be streaming — do not clobber it.
            if (streamingRef.current) return;
            setMsgs(
              conv.messages.map((m) => ({
                ...m,
                injected: isInjectedUserMessage(m),
              })),
            );
            setSummarized(!!conv.summarized);
            setSummaryPath(conv.summary_path ?? null);
          })
          .catch(() => {});
      }
    }
    return true;
  }

  return {
    streaming,
    liveElapsedMs,
    streamingAssistantIdxRef,
    streamingRef,
    runAgentStream,
    stopStreaming,
    ensureConversationId,
    resolveDocContext,
  };
}
