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

type UseAgentStreamOptions = {
  conversationId: string | null;
  previewPath?: string | null;
  webEnabled: boolean;
  msgs: ChatMessage[];
  setMsgs: Dispatch<SetStateAction<ChatMessage[]>>;
  setSummarized: Dispatch<SetStateAction<boolean>>;
  setSummaryPath: Dispatch<SetStateAction<string | null>>;
  /** 始终指向最新 conversationId，用于流结束后判断用户是否已切换到其他会话 */
  conversationIdRef: MutableRefObject<string | null>;
  /** 本地刚创建的对话 ID，流式结束前跳过从服务端拉历史（与 useChatConversation 共享） */
  skipLoadRef: MutableRefObject<string | null>;
  /** 是否正在流式中，与 useChatConversation 共享（避免 StrictMode 双次 effect 覆盖流式状态） */
  streamingRef: MutableRefObject<boolean>;
  /** 与 useChatScroll 共享的“是否粘底”标记，发送新消息时强制粘底 */
  stickToBottomRef: MutableRefObject<boolean>;
  onConversationCreated?: (id: string) => void;
  /** 发出该会话第一条用户问题时，用问题摘要更新侧边栏标题 */
  onFirstQuestionTitle?: (id: string, title: string) => void;
  onSidebarRefresh?: () => void;
  onKbChanged?: (changedPath?: string) => void;
};

export function useAgentStream({
  conversationId,
  previewPath,
  webEnabled,
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

  async function ensureConversationId(): Promise<string> {
    if (conversationId) return conversationId;
    const { id } = await createConversation();
    skipLoadRef.current = id;
    onConversationCreated?.(id);
    return id;
  }

  async function runAgentStream(apiText: string, userDisplayText?: string) {
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
      ts: new Date().toISOString(),
      timeline: [],
      sources: [],
    };
    setMsgs((m) => {
      const assistantIdx = m.length + 1;
      streamingAssistantIdxRef.current = assistantIdx;
      return [
        ...m,
        { role: "user", text: display, ts: new Date().toISOString() },
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

    try {
      const cid = await ensureConversationId();
      if (isFirstUserQuestion) {
        onFirstQuestionTitle?.(cid, titleFromText(display));
      }
      for await (const { event, data } of chatStream(
        apiText,
        cid,
        previewPath,
        webEnabled,
      )) {
        if (event === "error") {
          const message = (data.message as string) || "请求失败";
          patchAssistant((msg) => ({ ...msg, text: `错误：${message}` }));
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
            msg.ts = new Date().toISOString();
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
      const msg = err instanceof Error ? err.message : "请求失败";
      patchAssistant((prevMsg) => ({ ...prevMsg, text: `错误：${msg}` }));
    } finally {
      streamingRef.current = false;
      setStreaming(false);
      skipLoadRef.current = null;
      // 流关闭后服务端才完成 append_exchange（含标题），此时再刷新侧边栏
      onSidebarRefresh?.();
      const cid = conversationIdRef.current;
      if (cid) {
        getConversation(cid)
          .then((conv) => {
            if (conversationIdRef.current !== cid) return;
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
  };
}
