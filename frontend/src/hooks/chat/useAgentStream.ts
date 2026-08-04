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
  type SourceRef,
} from "../../api";
import { kbPathFromToolResult } from "../../utils/chatMessage";
import { nowIsoDisplay } from "../../utils/displayTime";

export type DocContext = { paths: string[]; primary: string | null };

type UseAgentStreamOptions = {
  conversationId: string | null;
  previewPath?: string | null;
  webEnabled: boolean;
  docPaths: string[];
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
};

export function useAgentStream({
  conversationId,
  previewPath: _previewPath,
  webEnabled,
  docPaths,
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
}: UseAgentStreamOptions) {
  const [streaming, setStreaming] = useState(false);
  const [liveElapsedMs, setLiveElapsedMs] = useState(0);
  const streamingStartRef = useRef<number | null>(null);
  const streamingAssistantIdxRef = useRef<number | null>(null);

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
    return { paths: docPaths, primary: primaryDocPath };
  }

  async function ensureConversationId(): Promise<string> {
    if (conversationId) return conversationId;
    const { id } = await createConversation();
    skipLoadRef.current = id;
    onConversationCreated?.(id);
    return id;
  }

  async function runAgentStream(
    apiText: string,
    userDisplayText?: string,
    userMeta?: Pick<ChatMessage, "attachments" | "doc_context" | "primary_doc">,
    docCtx?: DocContext,
  ) {
    if (streaming) return;
    const display = userDisplayText ?? apiText;
    const isFirstUserQuestion = !msgs.some((m) => m.role === "user");
    stickToBottomRef.current = true;
    setStreaming(true);
    streamingRef.current = true;
    streamingStartRef.current = Date.now();
    setLiveElapsedMs(0);

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
    try {
      const cid = await ensureConversationId();
      if (isFirstUserQuestion) {
        onFirstQuestionTitle?.(cid, titleFromText(display));
      }
      const ctx = docCtx ?? resolveDocContext();
      const clientMessageId = crypto.randomUUID();
      for await (const { event, data } of chatStream(apiText, {
        conversationId: cid,
        activeDocPaths: ctx.paths,
        primaryDocPath: ctx.primary,
        webEnabled,
        attachments: userMeta?.attachments ?? [],
        clientMessageId,
      })) {
        if (event === "error") {
          const message = (data.message as string) || "请求失败";
          patchAssistant((msg) => ({ ...msg, text: `错误：${message}` }));
          streamFailed = true;
          break;
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
        }
      }
    } catch (err) {
      streamFailed = true;
      const msg = err instanceof Error ? err.message : "请求失败";
      patchAssistant((prevMsg) => ({ ...prevMsg, text: `错误：${msg}` }));
    } finally {
      streamingRef.current = false;
      setStreaming(false);
      skipLoadRef.current = null;
      onSidebarRefresh?.();
      const cid = conversationIdRef.current;
      if (cid && !streamFailed) {
        getConversation(cid)
          .then((conv) => {
            if (conversationIdRef.current !== cid) return;
            setMsgs(conv.messages);
            setSummarized(!!conv.summarized);
            setSummaryPath(conv.summary_path ?? null);
          })
          .catch(() => {});
      }
    }
  }

  return {
    streaming,
    liveElapsedMs,
    streamingAssistantIdxRef,
    streamingRef,
    runAgentStream,
    ensureConversationId,
    resolveDocContext,
  };
}
