import { useEffect, useRef, useState } from "react";
import {
  chatStream,
  updateTimeline,
  uploadFile,
  downloadUrl,
  createConversation,
  getConversation,
  appendConversationMessages,
  type ChatMessage,
  type SourceRef,
} from "../api";
import { MarkdownContent } from "./MarkdownContent";
import { SourceChip } from "./SourceChip";
import { TimelineBlockView } from "./TimelineBlockView";

type Props = {
  conversationId: string | null;
  onConversationCreated?: (id: string) => void;
  onSidebarRefresh?: () => void;
  onOpenSource?: (src: SourceRef) => void;
};

const INPUT_MIN_HEIGHT = 40;
const INPUT_MAX_HEIGHT = 200;

export function Chat({
  conversationId,
  onConversationCreated,
  onSidebarRefresh,
  onOpenSource,
}: Props) {
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const skipLoadRef = useRef<string | null>(null);

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
    if (skipLoadRef.current === conversationId) {
      skipLoadRef.current = null;
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
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, loadingHistory]);

  async function ensureConversationId(): Promise<string> {
    if (conversationId) return conversationId;
    const { id } = await createConversation();
    skipLoadRef.current = id;
    onConversationCreated?.(id);
    return id;
  }

  async function send() {
    if (!input.trim() || streaming) return;
    const text = input;
    const userTs = new Date().toISOString();
    setMsgs((m) => [...m, { role: "user", text, ts: userTs }]);
    setInput("");
    setStreaming(true);

    const assistantMsg: ChatMessage = {
      role: "assistant",
      ts: new Date().toISOString(),
      timeline: [],
      sources: [],
    };
    setMsgs((m) => [...m, assistantMsg]);
    const assistantIdx = msgs.length + 1;

    try {
      const cid = await ensureConversationId();
      for await (const { event, data } of chatStream(text, cid)) {
        if (event === "error") {
          const message = (data.message as string) || "请求失败";
          setMsgs((prev) => {
            const copy = [...prev];
            copy[assistantIdx] = {
              ...copy[assistantIdx],
              text: `错误：${message}`,
            };
            return copy;
          });
          break;
        }

        setMsgs((prev) => {
          const copy = [...prev];
          const msg = { ...copy[assistantIdx] };
          if (event !== "done") {
            msg.timeline = updateTimeline(msg.timeline ?? [], event, data);
          }
          if (event === "done") {
            msg.sources = (data.sources as SourceRef[]) || [];
          }
          copy[assistantIdx] = msg;
          return copy;
        });

        if (event === "tool_result" && data.tool === "write_kb") {
          onSidebarRefresh?.();
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "请求失败";
      setMsgs((prev) => {
        const copy = [...prev];
        copy[assistantIdx] = {
          ...copy[assistantIdx],
          text: `错误：${msg}`,
        };
        return copy;
      });
    } finally {
      setStreaming(false);
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
      onSidebarRefresh?.();
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
    if (onOpenSource) {
      onOpenSource(src);
    } else if (src.type === "web" || src.type === "search") {
      window.open(src.url, "_blank", "noopener,noreferrer");
    }
  }

  function renderMessageContent(m: ChatMessage) {
    if (m.timeline && m.timeline.length > 0) {
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
          onOpenSource={handleOpenSource}
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

  return (
    <div className="chat-panel">
      <div className="chat-messages">
        {loadingHistory && <div className="chat-empty">加载对话中…</div>}
        {!loadingHistory && msgs.length === 0 && (
          <div className="chat-empty">
            直接输入即可。Agent 会自动检索知识库、搜索网页并整理到知识库。
          </div>
        )}
        {msgs.map((m, i) => (
          <div
            key={i}
            className={`chat-row ${m.role === "user" ? "chat-row-user" : "chat-row-assistant"}`}
          >
            <div className={`chat-bubble chat-bubble-${m.role}`}>
              {renderMessageContent(m)}
              {m.sources && m.sources.length > 0 && (
                <div className="chat-sources">
                  {m.sources.map((src, j) => (
                    <SourceChip
                      key={`${src.type}-${j}`}
                      source={src}
                      onOpenSource={handleOpenSource}
                    />
                  ))}
                </div>
              )}
              {m.attachments &&
                m.attachments.map((a) => (
                  <div key={a}>
                    <a href={downloadUrl(a)}>下载附件：{a.split("/").pop()}</a>
                  </div>
                ))}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <div className="chat-input-bar">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onInputKeyDown}
          rows={1}
          placeholder="输入问题或要记录的内容… Agent 会自动检索与整理（Enter 换行，Ctrl+Enter 发送）"
          disabled={streaming}
          style={{
            flex: 1,
            padding: 8,
            minHeight: INPUT_MIN_HEIGHT,
            maxHeight: INPUT_MAX_HEIGHT,
            resize: "none",
            lineHeight: 1.5,
          }}
        />
        <label style={{ padding: 8, cursor: "pointer" }}>
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
