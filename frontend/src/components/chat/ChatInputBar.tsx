import { useEffect, useRef } from "react";

const INPUT_MIN_HEIGHT = 34;
const INPUT_MAX_HEIGHT = 160;

export type ChatInputBarProps = {
  input: string;
  onInputChange: (value: string) => void;
  streaming: boolean;
  archiving: boolean;
  webEnabled: boolean;
  onToggleWebSearch: () => void;
  onFile: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onSend: () => void;
  onArchive: () => void;
  onViewArchive: () => void;
  summarized: boolean;
  summaryPath: string | null;
  conversationId: string | null;
  hasUserMessages: boolean;
};

export function ChatInputBar({
  input,
  onInputChange,
  streaming,
  archiving,
  webEnabled,
  onToggleWebSearch,
  onFile,
  onSend,
  onArchive,
  onViewArchive,
  summarized,
  summaryPath,
  conversationId,
  hasUserMessages,
}: ChatInputBarProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function adjustInputHeight() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const next = Math.min(
      Math.max(el.scrollHeight, INPUT_MIN_HEIGHT),
      INPUT_MAX_HEIGHT,
    );
    el.style.height = `${next}px`;
    el.style.overflowY =
      el.scrollHeight > INPUT_MAX_HEIGHT ? "auto" : "hidden";
  }

  useEffect(() => {
    adjustInputHeight();
  }, [input]);

  function onInputKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      onSend();
    }
  }

  return (
    <div className="chat-input-bar">
      <textarea
        ref={textareaRef}
        value={input}
        onChange={(e) => onInputChange(e.target.value)}
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
          onClick={onToggleWebSearch}
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
          onClick={onSend}
          disabled={streaming}
        >
          {streaming ? "处理中…" : "发送"}
        </button>
        <button
          type="button"
          className={`chat-archive-btn${summarized && summaryPath ? " chat-archive-btn--linked" : ""}`}
          onClick={
            summarized && summaryPath ? onViewArchive : onArchive
          }
          disabled={
            streaming ||
            archiving ||
            !conversationId ||
            (!summarized && !hasUserMessages)
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
  );
}
