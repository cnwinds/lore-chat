import { useEffect, useRef, useState } from "react";
import { useChatConversation } from "../hooks/chat/useChatConversation";
import { useChatScroll } from "../hooks/chat/useChatScroll";
import { useAgentStream } from "../hooks/chat/useAgentStream";
import {
  computeCumulative,
  formatDuration,
  getMessageCopyText,
  uploadFile,
  downloadUrl,
  appendConversationMessages,
  summarizeConversation,
  type ChatMessage,
  type IngestResult,
  type SourceRef,
} from "../api";
import { formatMessageTs, markToolBlockResolved } from "../utils/chatMessage";
import { MarkdownContent } from "./MarkdownContent";
import { ChatSources } from "./ChatSources";
import { CopyButton } from "./CopyButton";
import { TimelineBlockView } from "./TimelineBlockView";

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

const INPUT_MIN_HEIGHT = 34;
const INPUT_MAX_HEIGHT = 160;

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
  const textareaRef = useRef<HTMLTextAreaElement>(null);
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

  function adjustInputHeight() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const next = Math.min(Math.max(el.scrollHeight, INPUT_MIN_HEIGHT), INPUT_MAX_HEIGHT);
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > INPUT_MAX_HEIGHT ? "auto" : "hidden";
  }

  useEffect(() => {
    adjustInputHeight();
  }, [input]);

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

  function onInputKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      send();
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

  function getMessageDuration(m: ChatMessage): number | undefined {
    if (m.total_duration_ms !== undefined) return m.total_duration_ms;
    if (!m.timeline?.length) return undefined;
    const { toolCumulative, parallelCumulative } = computeCumulative(m.timeline);
    let max = 0;
    for (const v of toolCumulative.values()) max = Math.max(max, v);
    for (const v of parallelCumulative.values()) max = Math.max(max, v);
    return max > 0 ? max : undefined;
  }

  function renderMessageMeta(m: ChatMessage, isLive: boolean) {
    const copyText = getMessageCopyText(m);

    if (m.role === "user") {
      if (!copyText && !m.ts) return null;
      return (
        <div className="chat-meta chat-meta-user">
          {copyText && <CopyButton text={copyText} />}
          <span className="chat-meta-spacer" />
          {m.ts && <span>{formatMessageTs(m.ts)}</span>}
        </div>
      );
    }

    const durationMs = isLive ? liveElapsedMs : getMessageDuration(m);
    const timeStr = !isLive && m.ts ? formatMessageTs(m.ts) : null;
    if (!timeStr && (durationMs === undefined || durationMs <= 0) && !copyText) {
      return null;
    }

    return (
      <div className="chat-meta chat-meta-assistant">
        <div className="chat-meta-info">
          {timeStr && <span>{timeStr}</span>}
          {!isLive && durationMs !== undefined && durationMs > 0 && (
            <span>用时 {formatDuration(durationMs)}</span>
          )}
        </div>
        {copyText && !isLive && <CopyButton text={copyText} />}
      </div>
    );
  }

  function renderMessageContent(m: ChatMessage, isLive: boolean) {
    if (m.timeline && m.timeline.length > 0) {
      const cumulative = computeCumulative(m.timeline);
      return m.timeline.map((block, i) => (
        <TimelineBlockView
          key={
            block.type === "tool"
              ? block.id
              : block.type === "parallel"
                ? block.batch_id
                : `text-${i}`
          }
          block={block}
          cumulative={cumulative}
          liveElapsedMs={isLive ? liveElapsedMs : undefined}
          onOpenSource={handleOpenSource}
          previewPath={previewPath}
          conversationId={conversationId}
          onQuestionResolved={handleQuestionResolved}
        />
      ));
    }
    if (m.text) {
      if (m.role === "user") {
        return <div className="chat-user-text">{m.text}</div>;
      }
      return (
        <MarkdownContent className="markdown-body chat-markdown">
          {m.text}
        </MarkdownContent>
      );
    }
    return null;
  }

  function messageHasBody(m: ChatMessage, isLive: boolean): boolean {
    if (m.role === "user") return true;
    if (m.timeline?.length) return true;
    if (m.text) return true;
    if (m.sources?.length) return true;
    if (m.attachments?.length) return true;
    if (isLive) return false;
    return !!(m.ts || getMessageDuration(m) || getMessageCopyText(m));
  }

  return (
    <div className="chat-panel">
      <div className="chat-messages" ref={messagesContainerRef}>
        <div className="chat-messages-inner">
        {loadingHistory && <div className="chat-empty">加载对话中…</div>}
        {!loadingHistory && msgs.length === 0 && (
          <div className="chat-empty">
            直接输入即可。Agent 会自动检索知识库、搜索网页并整理到知识库。
          </div>
        )}
        {msgs.map((m, i) => {
          const isLiveStreaming =
            streaming && streamingAssistantIdxRef.current === i;
          if (!messageHasBody(m, isLiveStreaming)) {
            return null;
          }
          return (
          <div
            key={`${m.ts ?? "msg"}-${i}`}
            className={`chat-row ${m.role === "user" ? "chat-row-user" : "chat-row-assistant"}`}
          >
            <div className={`chat-bubble chat-bubble-${m.role}`}>
              {renderMessageContent(m, isLiveStreaming)}
              {m.sources && m.sources.length > 0 && (
                <ChatSources
                  sources={m.sources}
                  previewPath={previewPath}
                  onOpen={handleOpenSource}
                />
              )}
              {m.attachments &&
                m.attachments.map((a) => (
                  <div key={a}>
                    <a href={downloadUrl(a)}>下载附件：{a.split("/").pop()}</a>
                  </div>
                ))}
              {renderMessageMeta(m, isLiveStreaming)}
            </div>
          </div>
          );
        })}
        <div ref={messagesEndRef} className="chat-messages-anchor" aria-hidden />
        </div>
      </div>
      {streaming && (
        <div className="chat-streaming-wrap">
          <div className="chat-streaming-bar">
            <span className="chat-streaming-label">思考中…</span>
            {liveElapsedMs > 0 && (
              <span className="chat-streaming-duration">
                用时 {formatDuration(liveElapsedMs)}
              </span>
            )}
          </div>
        </div>
      )}
      <div className="chat-input-bar">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onInputKeyDown}
          rows={1}
          placeholder="输入问题或记录内容…（Ctrl+Enter 发送）"
          disabled={streaming}
          style={{
            minHeight: INPUT_MIN_HEIGHT,
            maxHeight: INPUT_MAX_HEIGHT,
          }}
        />
        <label className="chat-attach-btn" title="上传附件">
          📎
          <input type="file" hidden onChange={onFile} disabled={streaming} />
        </label>
        <div className="chat-input-actions">
          <button
            type="button"
            className={`chat-web-btn${webEnabled ? " chat-web-btn--on" : ""}`}
            onClick={toggleWebSearch}
            disabled={streaming}
            title={
              webEnabled
                ? "联网搜索：开（本地优先，联网补充）"
                : "联网搜索：关（仅本地知识库）"
            }
            aria-pressed={webEnabled}
          >
            🌐 联网
          </button>
          <button
            type="button"
            className="chat-send-btn"
            onClick={send}
            disabled={streaming}
          >
            {streaming ? "处理中…" : "发送"}
          </button>
          <button
            type="button"
            className={`chat-archive-btn${summarized && summaryPath ? " chat-archive-btn--linked" : ""}`}
            onClick={
              summarized && summaryPath
                ? () => onOpenDoc?.(summaryPath)
                : archiveConversation
            }
            disabled={
              streaming ||
              archiving ||
              !conversationId ||
              (!summarized && !msgs.some((m) => m.role === "user"))
            }
            title={
              summarized && summaryPath
                ? `查看归档文档：${summaryPath}`
                : "把整段会话通读后重构、去重，沉淀为一篇知识库文档"
            }
          >
            {archiving
              ? "沉淀中…"
              : summarized && summaryPath
                ? "查看文档"
                : "沉淀"}
          </button>
        </div>
      </div>
    </div>
  );
}

