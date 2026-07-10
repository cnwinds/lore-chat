import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  chatStream,
  computeCumulative,
  formatDuration,
  getMessageCopyText,
  updateTimeline,
  uploadFile,
  downloadUrl,
  createConversation,
  getConversation,
  appendConversationMessages,
  type ChatMessage,
  type IngestResult,
  type SourceRef,
  type TimelineBlock,
} from "../api";
import { MarkdownContent } from "./MarkdownContent";
import { ChatSources } from "./ChatSources";
import { CopyButton } from "./CopyButton";
import { TimelineBlockView } from "./TimelineBlockView";

type Props = {
  conversationId: string | null;
  previewPath?: string | null;
  onConversationCreated?: (id: string) => void;
  onSidebarRefresh?: () => void;
  onKbChanged?: (changedPath?: string) => void;
  onOpenSource?: (src: SourceRef) => void;
  onOpenDoc?: (path: string, excerpt?: string) => void;
};

function kbPathFromToolResult(data: Record<string, unknown>): string | undefined {
  const sources = data.sources as SourceRef[] | undefined;
  const kb = sources?.find((s) => s.type === "kb");
  return kb?.path;
}

const INPUT_MIN_HEIGHT = 34;
const INPUT_MAX_HEIGHT = 160;
const SCROLL_BOTTOM_THRESHOLD = 80;

function isNearBottom(container: HTMLElement): boolean {
  const distance =
    container.scrollHeight - container.scrollTop - container.clientHeight;
  return distance <= SCROLL_BOTTOM_THRESHOLD;
}

function formatMessageTs(ts: string): string {
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return "";
  }
}

function markToolBlockResolved(
  messages: ChatMessage[],
  blockId: string,
  choiceLabel: string,
): ChatMessage[] {
  function patchBlock(block: TimelineBlock): TimelineBlock {
    if (block.type === "tool" && block.id === blockId) {
      return { ...block, choice_resolved: choiceLabel };
    }
    if (block.type === "parallel") {
      return {
        ...block,
        children: block.children.map(patchBlock),
      };
    }
    return block;
  }
  return messages.map((msg) =>
    msg.timeline
      ? { ...msg, timeline: msg.timeline.map(patchBlock) }
      : msg,
  );
}

export function Chat({
  conversationId,
  previewPath,
  onConversationCreated,
  onSidebarRefresh,
  onKbChanged,
  onOpenSource,
  onOpenDoc,
}: Props) {
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [liveElapsedMs, setLiveElapsedMs] = useState(0);
  const streamingStartRef = useRef<number | null>(null);
  const streamingAssistantIdxRef = useRef<number | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  /** 本地刚创建的对话 ID，流式结束前跳过从服务端拉历史（避免 StrictMode 双次 effect 覆盖流式状态） */
  const skipLoadRef = useRef<string | null>(null);
  const streamingRef = useRef(false);

  function scrollMessagesToBottom() {
    const el = messagesContainerRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }

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

  useEffect(() => {
    if (!conversationId) {
      setMsgs([]);
      return;
    }
    if (skipLoadRef.current === conversationId || streamingRef.current) {
      return;
    }
    let cancelled = false;
    setLoadingHistory(true);
    getConversation(conversationId)
      .then((conv) => {
        if (!cancelled) setMsgs(conv.messages);
      })
      .catch(() => {
        if (!cancelled) setMsgs([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  useEffect(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const handleScroll = () => {
      stickToBottomRef.current = isNearBottom(el);
    };
    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  useLayoutEffect(() => {
    if (stickToBottomRef.current) {
      scrollMessagesToBottom();
    }
  }, [msgs, loadingHistory, streaming]);

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
      for await (const { event, data } of chatStream(apiText, cid, previewPath)) {
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

        if (event === "done") {
          onSidebarRefresh?.();
        }
        if (event === "tool_result") {
          if (data.tool === "write_kb") {
            onKbChanged?.(kbPathFromToolResult(data));
          } else if (data.tool === "delete_kb") {
            onKbChanged?.();
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
    }
  }

  async function send() {
    if (!input.trim() || streaming) return;
    const text = input;
    setInput("");
    await runAgentStream(text);
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
        <div className="chat-streaming-bar">
          <span className="chat-streaming-label">思考中…</span>
          {liveElapsedMs > 0 && (
            <span className="chat-streaming-duration">
              用时 {formatDuration(liveElapsedMs)}
            </span>
          )}
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
        <button onClick={send} disabled={streaming}>
          {streaming ? "处理中…" : "发送"}
        </button>
      </div>
    </div>
  );
}

