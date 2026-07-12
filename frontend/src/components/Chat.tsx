import { useEffect, useRef, useState } from "react";
import { useChatConversation } from "../hooks/chat/useChatConversation";
import { useChatScroll } from "../hooks/chat/useChatScroll";
import { useAgentStream } from "../hooks/chat/useAgentStream";
import {
  uploadFile,
  appendConversationMessages,
  summarizeConversation,
  type ChatMessage,
  type IngestResult,
  type SourceRef,
} from "../api";
import { markToolBlockResolved } from "../utils/chatMessage";
import { ChatMessageList } from "./chat/ChatMessageList";
import { ChatInputBar } from "./chat/ChatInputBar";

type Props = {
  conversationId: string | null;
  previewPath?: string | null;
  onConversationCreated?: (id: string) => void;
  /** 发出该会话第一条用户问题时，用问题摘要更新侧边栏标题 */
  onFirstQuestionTitle?: (id: string, title: string) => void;
  onSidebarRefresh?: () => void;
  onKbChanged?: (changedPath?: string) => void;
  onOpenSource?: (src: SourceRef) => void;
  onOpenDoc?: (path: string, excerpt?: string) => void;
};

export function Chat({
  conversationId,
  previewPath,
  onConversationCreated,
  onFirstQuestionTitle,
  onSidebarRefresh,
  onKbChanged,
  onOpenSource,
  onOpenDoc,
}: Props) {
  const [input, setInput] = useState("");
  const [archiving, setArchiving] = useState(false);
  const [webEnabled, setWebEnabled] = useState<boolean>(
    () => localStorage.getItem("lorechat.webSearch") === "1",
  );
  const messagesEndRef = useRef<HTMLDivElement>(null);
  /** 本地刚创建的对话 ID，流式结束前跳过从服务端拉历史（避免 StrictMode 双次 effect 覆盖流式状态） */
  const skipLoadRef = useRef<string | null>(null);
  const streamingRef = useRef(false);
  const conversationIdRef = useRef(conversationId);
  const {
    msgs,
    setMsgs,
    loadingHistory,
    summarized,
    setSummarized,
    summaryPath,
    setSummaryPath,
  } = useChatConversation({ conversationId, skipLoadRef, streamingRef });
  const stickToBottomRef = useRef(true);
  const {
    streaming,
    liveElapsedMs,
    streamingAssistantIdxRef,
    runAgentStream,
    ensureConversationId,
  } = useAgentStream({
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
  });
  const { messagesContainerRef } = useChatScroll(
    [msgs, loadingHistory, streaming],
    stickToBottomRef,
  );

  useEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);

  function toggleWebSearch() {
    setWebEnabled((prev) => {
      const next = !prev;
      localStorage.setItem("lorechat.webSearch", next ? "1" : "0");
      return next;
    });
  }

  async function send() {
    if (!input.trim() || streaming) return;
    const text = input;
    setInput("");
    await runAgentStream(text);
  }

  async function archiveConversation() {
    if (!conversationId || streaming || archiving) return;
    if (!msgs.some((m) => m.role === "user")) return;
    const targetCid = conversationId;
    setArchiving(true);
    try {
      const result = await summarizeConversation(targetCid);
      // 沉淀耗时较长，用户可能已切到其他会话；只把结果写回发起沉淀的那条会话
      if (conversationIdRef.current !== targetCid) {
        onSidebarRefresh?.();
        if (result.rel_path) onKbChanged?.(result.rel_path);
        return;
      }
      const text =
        result.status === "saved" && result.rel_path
          ? `已把本次会话归档为文档：${result.rel_path}`
          : result.message || "归档完成";
      setMsgs((m) => [
        ...m,
        { role: "assistant", text, ts: new Date().toISOString() },
      ]);
      if (result.rel_path) {
        setSummarized(true);
        setSummaryPath(result.rel_path);
        onKbChanged?.(result.rel_path);
        onOpenDoc?.(result.rel_path);
      }
      onSidebarRefresh?.();
    } catch (err) {
      if (conversationIdRef.current !== targetCid) {
        onSidebarRefresh?.();
        return;
      }
      const msg = err instanceof Error ? err.message : "归档失败";
      setMsgs((m) => [
        ...m,
        { role: "assistant", text: `错误：${msg}`, ts: new Date().toISOString() },
      ]);
    } finally {
      setArchiving(false);
    }
  }

  function handleQuestionResolved(
    blockId: string,
    result: IngestResult,
    choiceLabel: string,
  ) {
    setMsgs((prev) => markToolBlockResolved(prev, blockId, choiceLabel));
    onKbChanged?.(result.rel_path ?? undefined);

    if (result.status === "continue" && result.continue_prompt) {
      void runAgentStream(result.continue_prompt, choiceLabel);
      return;
    }
    if (result.status === "saved" && result.message) {
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          text: result.message,
          ts: new Date().toISOString(),
        },
      ]);
      if (result.rel_path) {
        onOpenDoc?.(result.rel_path);
      }
      return;
    }
    if (result.status === "acknowledged") {
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          text: result.message,
          ts: new Date().toISOString(),
        },
      ]);
    }
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    try {
      const r = await uploadFile(f, "未分类");
      const assistantMsg: ChatMessage = {
        role: "assistant",
        intent: "remember",
        text: `已保存文件：${r.attachment}`,
      };
      const cid = await ensureConversationId();
      await appendConversationMessages(cid, [assistantMsg]);
      setMsgs((m) => [...m, assistantMsg]);
      onKbChanged?.(r.attachment);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "上传失败";
      setMsgs((m) => [...m, { role: "assistant", text: `错误：${msg}` }]);
    } finally {
      e.target.value = "";
    }
  }

  function handleOpenSource(src: SourceRef) {
    if (src.type === "conversation") {
      // 未归档会话来源仅作展示，暂不跳转
      return;
    }
    if (src.type === "kb" && src.path) {
      if (onOpenDoc) {
        onOpenDoc(src.path, src.excerpt);
      } else {
        onOpenSource?.(src);
      }
      return;
    }
    if (onOpenSource) {
      onOpenSource(src);
    } else if (src.type === "web" || src.type === "search") {
      window.open(src.url, "_blank", "noopener,noreferrer");
    }
  }

  return (
    <div className="chat-panel">
      <ChatMessageList
        msgs={msgs}
        loadingHistory={loadingHistory}
        streaming={streaming}
        liveElapsedMs={liveElapsedMs}
        streamingAssistantIdxRef={streamingAssistantIdxRef}
        messagesContainerRef={messagesContainerRef}
        messagesEndRef={messagesEndRef}
        previewPath={previewPath}
        conversationId={conversationId}
        onOpenSource={handleOpenSource}
        onQuestionResolved={handleQuestionResolved}
      />
      <ChatInputBar
        input={input}
        onInputChange={setInput}
        streaming={streaming}
        archiving={archiving}
        webEnabled={webEnabled}
        onToggleWebSearch={toggleWebSearch}
        onFile={onFile}
        onSend={send}
        onArchive={archiveConversation}
        onViewArchive={() => {
          if (summaryPath) onOpenDoc?.(summaryPath);
        }}
        summarized={summarized}
        summaryPath={summaryPath}
        conversationId={conversationId}
        hasUserMessages={msgs.some((m) => m.role === "user")}
      />
    </div>
  );
}
